"""
Task API Router
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from config import Config
from database import get_db
from models import TaskCreate, TaskReview, TaskUpdate
from security import rate_limit, verify_api_key
from utils import (
    check_circular_dependency,
    check_dependencies,
    check_idempotency,
    log_task_action,
    restore_soft_deleted,
    soft_delete,
    store_idempotency_response,
    update_agent_status_after_task_change,
    validate_task_dependencies_for_create,
)

router = APIRouter()


@router.post("/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def create_task(task: TaskCreate, db=Depends(get_db)):
    """创建任务

    如果指定了 dependencies，会检查是否存在循环依赖。
    """
    # 基础验证
    if task.dependencies:
        validate_task_dependencies_for_create(task.dependencies)

    async with db.acquire() as conn:
        # 检查循环依赖
        if task.dependencies:
            has_cycle = await check_circular_dependency(conn, None, task.dependencies)
            if has_cycle:
                raise HTTPException(status_code=400, detail="Circular dependency detected")

        result = await conn.fetchrow(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type, priority,
                assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                parent_task_id, dependencies, task_tags, estimated_hours, timeout_minutes, created_by, due_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING *
            """,
            task.project_id, task.title, task.description, task.task_type, task.priority,
            task.assignee_agent, task.reviewer_id, task.reviewer_mention, task.acceptance_criteria,
            task.parent_task_id, task.dependencies, task.task_tags, task.estimated_hours,
            task.timeout_minutes, task.created_by, task.due_at
        )
    return result


@router.get("/", dependencies=[Depends(rate_limit)])
async def list_tasks(
    project_id: int | None = None,
    status: str | None = None,
    assignee: str | None = None,
    task_type: str | None = None,
    tags: list[str] | None = Query(None),
    db=Depends(get_db)
):
    """列出任务，支持多种过滤条件"""
    conditions = ["1=1"]
    params = []

    if project_id:
        params.append(project_id)
        conditions.append(f"project_id = ${len(params)}")
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if assignee:
        params.append(assignee)
        conditions.append(f"assignee_agent = ${len(params)}")
    if task_type:
        params.append(task_type)
        conditions.append(f"task_type = ${len(params)}")
    if tags:
        params.append(tags)
        conditions.append(f"task_tags && ${len(params)}")

    query = f"SELECT * FROM tasks WHERE {' AND '.join(conditions)} AND deleted_at IS NULL ORDER BY priority DESC, created_at DESC"

    async with db.acquire() as conn:
        results = await conn.fetch(query, *params)
    return results


@router.get("/available", dependencies=[Depends(rate_limit)])
async def get_available_tasks(db=Depends(get_db)):
    """获取可认领的任务（pending 状态，没有 assignee，依赖已完成）"""
    async with db.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT t.*
            FROM tasks t
            WHERE t.status = 'pending'
            AND t.assignee_agent IS NULL
            AND t.deleted_at IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM tasks dep
                WHERE dep.id = ANY(t.dependencies)
                AND dep.status != 'completed'
                AND dep.deleted_at IS NULL
            )
            ORDER BY t.priority DESC, t.created_at ASC
            """
        )
    return [dict(row) for row in results]


@router.get("/available-for/{agent_name}", dependencies=[Depends(rate_limit)])
async def get_available_tasks_for_agent(
    agent_name: str,
    skill_match: bool = True,
    db=Depends(get_db)
):
    """获取适合某 Agent 的任务（带技能匹配）"""
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent_skills = agent["skills"] or []

        if skill_match and agent_skills:
            results = await conn.fetch(
                """
                SELECT t.*
                FROM tasks t
                WHERE t.status = 'pending'
                AND t.assignee_agent IS NULL
                AND t.deleted_at IS NULL
                AND t.task_tags && $1
                AND NOT EXISTS (
                    SELECT 1 FROM tasks dep
                    WHERE dep.id = ANY(t.dependencies)
                    AND dep.status != 'completed'
                    AND dep.deleted_at IS NULL
                )
                ORDER BY t.priority DESC, t.created_at ASC
                """,
                agent_skills
            )
        else:
            results = await conn.fetch(
                """
                SELECT t.*
                FROM tasks t
                WHERE t.status = 'pending'
                AND t.assignee_agent IS NULL
                AND t.deleted_at IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM tasks dep
                    WHERE dep.id = ANY(t.dependencies)
                    AND dep.status != 'completed'
                    AND dep.deleted_at IS NULL
                )
                ORDER BY t.priority DESC, t.created_at ASC
                """
            )
    return [dict(row) for row in results]


@router.post("/{task_id}/claim/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def claim_task(
    task_id: int,
    agent_name: str,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """Agent 认领任务（带依赖检查、事务锁定和幂等性）

    使用事务确保依赖检查和任务认领的原子性，彻底消除竞态条件。
    """
    MAX_CONCURRENT_TASKS = Config.MAX_CONCURRENT_TASKS_PER_AGENT

    async with db.acquire() as conn:
        async with conn.transaction():
            # 检查幂等性
            cached, should_skip = await check_idempotency(conn, idempotency_key)
            if should_skip:
                return cached

            # 锁定当前任务，防止并发修改
            task_row = await conn.fetchrow(
                "SELECT id, dependencies, status, assignee_agent FROM tasks WHERE id = $1 FOR UPDATE",
                task_id
            )
            if not task_row:
                raise HTTPException(status_code=404, detail="Task not found")

            if task_row["status"] != "pending" or task_row["assignee_agent"] is not None:
                raise HTTPException(status_code=409, detail="Task already claimed by another agent or not available")

            # 检查依赖（使用 FOR UPDATE 锁定依赖任务）
            deps_ok, deps = await check_dependencies(conn, task_id, for_update=True)
            if not deps_ok:
                raise HTTPException(status_code=400, detail=f"Dependencies not completed: {deps}")

            # 检查并发任务数（锁定 Agent 记录）
            current_tasks = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE assignee_agent = $1 AND status IN ('assigned', 'running', 'reviewing')
                """,
                agent_name
            )

            if current_tasks['count'] >= MAX_CONCURRENT_TASKS:
                raise HTTPException(
                    status_code=429,
                    detail=f"Agent {agent_name} has reached maximum concurrent tasks limit ({MAX_CONCURRENT_TASKS})"
                )

            # 原子性更新任务
            result = await conn.fetchrow(
                """
                UPDATE tasks
                SET assignee_agent = $1, status = 'assigned', assigned_at = NOW(), updated_at = NOW()
                WHERE id = $2
                RETURNING *
                """,
                agent_name, task_id
            )

            # 更新 Agent 状态
            await conn.execute(
                """
                UPDATE agents
                SET status = 'busy', current_task_id = $1, updated_at = NOW()
                WHERE name = $2
                """,
                task_id, agent_name
            )

            await log_task_action(
                conn, task_id, "claimed", "pending", "assigned", f"Task claimed by {agent_name}", agent_name
            )

            response = dict(result)
            await store_idempotency_response(conn, idempotency_key, response)

    return result


@router.post("/{task_id}/start/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def start_task(
    task_id: int,
    agent_name: str,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """Agent 开始执行任务（支持幂等性）"""
    async with db.acquire() as conn:
        # 检查幂等性
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached

        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")

        if task["status"] != "assigned":
            raise HTTPException(status_code=400, detail=f"Cannot start task with status: {task['status']}")

        running_task = await conn.fetchrow(
            "SELECT id, title FROM tasks WHERE assignee_agent = $1 AND status = 'running'",
            agent_name
        )
        if running_task:
            raise HTTPException(
                status_code=409,
                detail=f"Already has a running task (#{running_task['id']} - {running_task['title']}). "
                       f"Please complete or release it before starting a new one."
            )

        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'running', started_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )

        await log_task_action(
            conn, task_id, "started", "assigned", "running", f"Task started by {agent_name}", agent_name
        )

        # 存储幂等响应
        response = dict(result)
        await store_idempotency_response(conn, idempotency_key, response)

    return result


@router.post("/{task_id}/submit/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def submit_task(
    task_id: int,
    agent_name: str,
    result: dict,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """Agent 提交任务完成，进入验收阶段"""
    async with db.acquire() as conn:
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached

        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")

        if task["status"] != "running":
            raise HTTPException(status_code=400, detail=f"Cannot submit task with status: {task['status']}")

        updated = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'reviewing', result = $1, updated_at = NOW()
            WHERE id = $2
            RETURNING *
            """,
            json.dumps(result), task_id
        )

        await log_task_action(
            conn, task_id, "submitted", "running", "reviewing", f"Task submitted for review by {agent_name}", agent_name
        )

        response = dict(updated)
        await store_idempotency_response(conn, idempotency_key, response)

    return updated


@router.post("/{task_id}/release/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def release_task(
    task_id: int,
    agent_name: str,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """Agent 释放任务（重新变成 pending，支持幂等性）"""
    async with db.acquire() as conn:
        # 检查幂等性
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached

        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")

        if task["status"] not in ["assigned", "running"]:
            raise HTTPException(status_code=400, detail=f"Cannot release task with status: {task['status']}")

        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET assignee_agent = NULL, status = 'pending', assigned_at = NULL, started_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )

        await update_agent_status_after_task_change(conn, agent_name)

        await log_task_action(
            conn, task_id, "released", task["status"], "pending", f"Task released by {agent_name}", agent_name
        )

        # 存储幂等响应
        response = dict(result)
        await store_idempotency_response(conn, idempotency_key, response)

    return result


@router.post("/{task_id}/retry/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def retry_task(
    task_id: int,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """重试失败或被拒绝的任务（支持幂等性）"""
    async with db.acquire() as conn:
        # 检查幂等性
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached

        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task["status"] not in ["failed", "rejected"]:
            raise HTTPException(status_code=400, detail=f"Cannot retry task with status: {task['status']}")

        if task["retry_count"] >= task["max_retries"]:
            raise HTTPException(status_code=400, detail=f"Max retries ({task['max_retries']}) exceeded")

        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'pending', assignee_agent = NULL, retry_count = retry_count + 1,
                assigned_at = NULL, started_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )

        await log_task_action(
            conn, task_id, "retry", task["status"], "pending", f"Task retry (attempt {result['retry_count']})", "system"
        )

        # 存储幂等响应
        response = dict(result)
        await store_idempotency_response(conn, idempotency_key, response)

    return result


@router.get("/{task_id}", dependencies=[Depends(rate_limit)])
async def get_task(task_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1 AND deleted_at IS NULL", task_id)
        logs = await conn.fetch(
            "SELECT * FROM task_logs WHERE task_id = $1 ORDER BY created_at DESC",
            task_id
        )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": dict(task), "logs": [dict(log) for log in logs]}


@router.patch("/{task_id}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def update_task(task_id: int, update: TaskUpdate, db=Depends(get_db)):
    async with db.acquire() as conn:
        async with conn.transaction():
            current = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1 AND deleted_at IS NULL", task_id)
            if not current:
                raise HTTPException(status_code=404, detail="Task not found")

            updates = []
            params = []
            param_num = 1

            if update.status is not None:
                updates.append(f"status = ${param_num}")
                params.append(update.status)
                param_num += 1

                if update.status == "completed":
                    updates.append("completed_at = NOW()")

                    if current["assignee_agent"]:
                        await conn.execute(
                            """
                            UPDATE agents
                            SET completed_tasks = completed_tasks + 1,
                                total_tasks = total_tasks + 1,
                                success_rate = (completed_tasks::FLOAT + 1) / NULLIF(total_tasks + 1, 0),
                                updated_at = NOW()
                            WHERE name = $1
                            """,
                            current["assignee_agent"]
                        )
                        await update_agent_status_after_task_change(conn, current["assignee_agent"])
                elif update.status == "failed":
                    if current["assignee_agent"]:
                        await conn.execute(
                            """
                            UPDATE agents
                            SET failed_tasks = failed_tasks + 1,
                                total_tasks = total_tasks + 1,
                                success_rate = (completed_tasks::FLOAT) / NULLIF(total_tasks + 1, 0),
                                updated_at = NOW()
                            WHERE name = $1
                            """,
                            current["assignee_agent"]
                        )
                        await update_agent_status_after_task_change(conn, current["assignee_agent"])

            if update.result is not None:
                updates.append(f"result = ${param_num}")
                params.append(json.dumps(update.result))
                param_num += 1

            if update.assignee_agent is not None:
                updates.append(f"assignee_agent = ${param_num}")
                params.append(update.assignee_agent)
                param_num += 1

            if update.priority is not None:
                updates.append(f"priority = ${param_num}")
                params.append(update.priority)
                param_num += 1

            if update.feedback is not None:
                updates.append(f"feedback = ${param_num}")
                params.append(update.feedback)
                param_num += 1

            if not updates:
                return current

            updates.append("updated_at = NOW()")
            params.append(task_id)

            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ${param_num} AND deleted_at IS NULL RETURNING *"

            result = await conn.fetchrow(query, *params)

            await conn.execute(
                """
                INSERT INTO task_logs (task_id, action, old_status, new_status, message)
                VALUES ($1, $2, $3, $4, $5)
                """,
                task_id, "status_changed", current["status"], update.status or current["status"],
                f"Task updated: {update.dict(exclude_none=True)}"
            )

    return result


@router.post("/{task_id}/review/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def review_task(
    task_id: int,
    review: TaskReview,
    reviewer: str,
    idempotency_key: str | None = None,
    db=Depends(get_db)
):
    """验收任务 - 支持通过、拒绝（支持幂等性）"""
    async with db.acquire() as conn:
        async with conn.transaction():
            # 检查幂等性
            cached, should_skip = await check_idempotency(conn, idempotency_key)
            if should_skip:
                return cached

            task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1 AND deleted_at IS NULL", task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            if task["status"] != "reviewing":
                raise HTTPException(status_code=400, detail=f"Cannot review task with status: {task['status']}")

            if review.approved:
                new_status = "completed"
                if task["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents
                        SET completed_tasks = completed_tasks + 1,
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        task["assignee_agent"]
                    )
                    await update_agent_status_after_task_change(conn, task["assignee_agent"])
            else:
                new_status = "rejected"
                if task["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents
                            SET failed_tasks = failed_tasks + 1,
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        task["assignee_agent"]
                    )
                    await update_agent_status_after_task_change(conn, task["assignee_agent"])

            await conn.execute(
                """
                UPDATE tasks SET status = $1, feedback = $2, updated_at = NOW(),
                    completed_at = CASE WHEN $1::varchar = 'completed' THEN NOW() ELSE NULL END
                WHERE id = $3 AND deleted_at IS NULL
                """,
                new_status, review.feedback, task_id
            )

            await log_task_action(
                conn, task_id, "reviewed", task["status"], new_status,
                f"Reviewed by {reviewer}: {'approved' if review.approved else 'rejected'}. Feedback: {review.feedback}",
                reviewer
            )

            updated = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)

            # 存储幂等响应
            response = dict(updated)
            await store_idempotency_response(conn, idempotency_key, response)

    return updated


@router.delete("/{task_id}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def delete_task(
    task_id: int,
    hard: bool = False,
    db=Depends(get_db)
):
    """删除任务（默认软删除，hard=true 时物理删除）"""
    async with db.acquire() as conn:
        if hard:
            # 物理删除
            from utils import hard_delete
            success = await hard_delete(conn, "tasks", task_id)
        else:
            # 软删除
            success = await soft_delete(conn, "tasks", task_id)

    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already deleted")

    return {"message": f"Task {task_id} {'hard ' if hard else ''}deleted successfully"}


@router.post("/{task_id}/restore", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def restore_task(task_id: int, db=Depends(get_db)):
    """恢复软删除的任务"""
    async with db.acquire() as conn:
        success = await restore_soft_deleted(conn, "tasks", task_id)

    if not success:
        raise HTTPException(status_code=404, detail="Task not found or not deleted")

    return {"message": f"Task {task_id} restored successfully"}
