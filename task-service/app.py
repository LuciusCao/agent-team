#!/usr/bin/env python3
"""
Task Management Service v1.1
FastAPI + PostgreSQL
Agent Workforce Extensions
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncpg

app = FastAPI(title="Task Management Service", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/taskmanager")
pool: Optional[asyncpg.Pool] = None


async def get_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return pool


# ============ Pydantic Models ============

class AgentRegister(BaseModel):
    name: str
    discord_user_id: Optional[str] = None
    role: str
    capabilities: Optional[dict] = None
    skills: Optional[List[str]] = None


class AgentHeartbeat(BaseModel):
    name: str
    current_task_id: Optional[int] = None


class AgentChannel(BaseModel):
    agent_name: str
    channel_id: str


class ProjectCreate(BaseModel):
    name: str
    discord_channel_id: Optional[str] = None
    description: Optional[str] = None


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    task_type: str
    priority: Optional[int] = 5
    assignee_agent: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_mention: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    parent_task_id: Optional[int] = None
    dependencies: Optional[List[int]] = None
    task_tags: Optional[List[str]] = None
    estimated_hours: Optional[float] = None
    created_by: Optional[str] = None
    due_at: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict] = None
    assignee_agent: Optional[str] = None
    priority: Optional[int] = None
    feedback: Optional[str] = None


class TaskReview(BaseModel):
    approved: bool
    feedback: Optional[str] = None


# ============ Dependency Check ============

async def check_dependencies(conn: asyncpg.Connection, task_id: int) -> tuple[bool, List[int]]:
    """检查任务依赖是否完成"""
    task = await conn.fetchrow("SELECT dependencies FROM tasks WHERE id = $1", task_id)
    if not task or not task["dependencies"]:
        return True, []
    
    deps = task["dependencies"]
    
    # 检查所有依赖任务是否完成
    for dep_id in deps:
        dep = await conn.fetchrow(
            "SELECT status FROM tasks WHERE id = $1",
            dep_id
        )
        if not dep or dep["status"] != "completed":
            return False, deps
    
    return True, []


# ============ API Routes ============

@app.get("/")
async def root():
    return {"status": "ok", "service": "task-management", "version": "1.1.0"}


# ============ Project Endpoints ============

@app.post("/projects")
async def create_project(project: ProjectCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO projects (name, discord_channel_id, description)
            VALUES ($1, $2, $3)
            RETURNING id, name, discord_channel_id, description, status, created_at
            """,
            project.name, project.discord_channel_id, project.description
        )
    return result


@app.get("/projects")
async def list_projects(status: Optional[str] = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if status:
            results = await conn.fetch(
                "SELECT * FROM projects WHERE status = $1 ORDER BY created_at DESC",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM projects ORDER BY created_at DESC")
    return results


@app.get("/projects/{project_id}")
async def get_project(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/projects/{project_id}/progress")
async def get_project_progress(project_id: int, db=Depends(get_db)):
    """获取项目进度统计"""
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 统计任务状态
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'assigned') as assigned,
                COUNT(*) FILTER (WHERE status = 'running') as running,
                COUNT(*) FILTER (WHERE status = 'reviewing') as reviewing,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'rejected') as rejected
            FROM tasks WHERE project_id = $1
            """,
            project_id
        )
        
        total = stats["total"] or 0
        completed = stats["completed"] or 0
        progress = (completed / total * 100) if total > 0 else 0
    
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "total_tasks": total,
        "stats": dict(stats),
        "progress_percent": round(progress, 1)
    }


@app.post("/projects/{project_id}/breakdown")
async def breakdown_project(project_id: int, tasks: List[TaskCreate], db=Depends(get_db)):
    """项目拆分：批量创建任务"""
    async with db.acquire() as conn:
        # 检查项目存在
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        created_tasks = []
        for task in tasks:
            result = await conn.fetchrow(
                """
                INSERT INTO tasks (
                    project_id, title, description, task_type, priority,
                    assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                    parent_task_id, dependencies, task_tags, estimated_hours, created_by, due_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING *
                """,
                project_id, task.title, task.description, task.task_type, task.priority,
                task.assignee_agent, task.reviewer_id, task.reviewer_mention, task.acceptance_criteria,
                task.parent_task_id, task.dependencies, task.task_tags, task.estimated_hours,
                task.created_by, task.due_at
            )
            
            # 记录日志
            await conn.execute(
                "INSERT INTO task_logs (task_id, action, message, actor) VALUES ($1, $2, $3, $4)",
                result["id"], "created", f"Task created via breakdown: {task.title}", task.created_by or "system"
            )
            
            created_tasks.append(dict(result))
    
    return {"project_id": project_id, "tasks_created": len(created_tasks), "tasks": created_tasks}


# ============ Task Endpoints ============

@app.post("/tasks")
async def create_task(task: TaskCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type, priority,
                assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                parent_task_id, dependencies, task_tags, estimated_hours, created_by, due_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
            """,
            task.project_id, task.title, task.description, task.task_type, task.priority,
            task.assignee_agent, task.reviewer_id, task.reviewer_mention, task.acceptance_criteria,
            task.parent_task_id, task.dependencies, task.task_tags, task.estimated_hours,
            task.created_by, task.due_at
        )
        
        await conn.execute(
            "INSERT INTO task_logs (task_id, action, message, actor) VALUES ($1, $2, $3, $4)",
            result["id"], "created", f"Task created: {task.title}", task.created_by or "system"
        )
    return result


@app.get("/tasks")
async def list_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    task_type: Optional[str] = None,
    tags: Optional[List[str]] = Query(None),
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
        # 检查是否包含任一标签
        params.append(tags)
        conditions.append(f"task_tags && ${len(params)}")
    
    query = f"SELECT * FROM tasks WHERE {' AND '.join(conditions)} ORDER BY priority DESC, created_at DESC"
    
    async with db.acquire() as conn:
        results = await conn.fetch(query, *params)
    return results


@app.get("/tasks/available")
async def get_available_tasks(db=Depends(get_db)):
    """获取可认领的任务（pending 状态，没有 assignee，依赖已完成）"""
    async with db.acquire() as conn:
        # 获取所有 pending 且未分配的任务
        pending = await conn.fetch(
            """
            SELECT * FROM tasks 
            WHERE status = 'pending' AND assignee_agent IS NULL
            ORDER BY priority DESC, created_at ASC
            """
        )
        
        # 过滤掉依赖未完成的任务
        available = []
        for task in pending:
            deps_ok, _ = await check_dependencies(conn, task["id"])
            if deps_ok:
                available.append(dict(task))
    
    return available


@app.get("/tasks/available-for/{agent_name}")
async def get_available_tasks_for_agent(
    agent_name: str,
    skill_match: bool = True,
    db=Depends(get_db)
):
    """获取适合某 Agent 的任务（带技能匹配）"""
    async with db.acquire() as conn:
        # 获取 Agent 信息
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # 获取所有 pending 且未分配的任务
        pending = await conn.fetch(
            """
            SELECT * FROM tasks 
            WHERE status = 'pending' AND assignee_agent IS NULL
            ORDER BY priority DESC, created_at ASC
            """
        )
        
        # 过滤：依赖完成 + 技能匹配（可选）
        available = []
        agent_skills = set(agent["skills"] or [])
        
        for task in pending:
            # 检查依赖
            deps_ok, _ = await check_dependencies(conn, task["id"])
            if not deps_ok:
                continue
            
            # 技能匹配
            if skill_match and agent_skills:
                task_tags = set(task["task_tags"] or [])
                # 有共同标签才算匹配
                if not (agent_skills & task_tags):
                    continue
            
            available.append(dict(task))
    
    return available


@app.post("/tasks/{task_id}/claim")
async def claim_task(task_id: int, agent_name: str, db=Depends(get_db)):
    """Agent 认领任务（带依赖检查和乐观锁）"""
    async with db.acquire() as conn:
        # 检查依赖
        deps_ok, deps = await check_dependencies(conn, task_id)
        if not deps_ok:
            raise HTTPException(status_code=400, detail=f"Dependencies not completed: {deps}")
        
        # 检查任务是否存在且可认领（乐观锁）
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND status = 'pending' AND assignee_agent IS NULL",
            task_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not available or already claimed")
        
        # 更新 Agent 状态
        await conn.execute(
            """
            UPDATE agents 
            SET status = 'busy', current_task_id = $1, updated_at = NOW()
            WHERE name = $2
            """,
            task_id, agent_name
        )
        
        # 认领任务
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET assignee_agent = $1, status = 'assigned', assigned_at = NOW(), updated_at = NOW()
            WHERE id = $2
            RETURNING *
            """,
            agent_name, task_id
        )
        
        # 记录日志
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "claimed", "pending", "assigned", f"Task claimed by {agent_name}", agent_name
        )
    
    return result


@app.post("/tasks/{task_id}/start")
async def start_task(task_id: int, agent_name: str, db=Depends(get_db)):
    """Agent 开始执行任务"""
    async with db.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
        
        if task["status"] != "assigned":
            raise HTTPException(status_code=400, detail=f"Cannot start task with status: {task['status']}")
        
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'running', started_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "started", "assigned", "running", f"Task started by {agent_name}", agent_name
        )
    
    return result


@app.post("/tasks/{task_id}/submit")
async def submit_task(task_id: int, agent_name: str, result: dict, db=Depends(get_db)):
    """Agent 提交任务完成，进入验收阶段"""
    async with db.acquire() as conn:
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
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "submitted", "running", "reviewing", f"Task submitted for review by {agent_name}", agent_name
        )
    
    return updated


@app.post("/tasks/{task_id}/release")
async def release_task(task_id: int, agent_name: str, db=Depends(get_db)):
    """Agent 释放任务（重新变成 pending）"""
    async with db.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
        
        # 只能释放 assigned 或 running 状态的任务
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
        
        # 更新 Agent 状态
        await conn.execute(
            """
            UPDATE agents 
            SET status = 'online', current_task_id = NULL, updated_at = NOW()
            WHERE name = $1
            """,
            agent_name
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "released", task["status"], "pending", f"Task released by {agent_name}", agent_name
        )
    
    return result


@app.post("/tasks/{task_id}/retry")
async def retry_task(task_id: int, db=Depends(get_db)):
    """重试失败或被拒绝的任务"""
    async with db.acquire() as conn:
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
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "retry", task["status"], "pending", f"Task retry (attempt {result['retry_count']})", "system"
        )
    
    return result


@app.get("/tasks/{task_id}")
async def get_task(task_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        logs = await conn.fetch(
            "SELECT * FROM task_logs WHERE task_id = $1 ORDER BY created_at DESC",
            task_id
        )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": dict(task), "logs": [dict(l) for l in logs]}


@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate, db=Depends(get_db)):
    async with db.acquire() as conn:
        current = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not current:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 构建更新
        updates = []
        params = []
        param_num = 1
        
        if update.status is not None:
            updates.append(f"status = ${param_num}")
            params.append(update.status)
            param_num += 1
            
            if update.status == "completed":
                updates.append("completed_at = NOW()")
                
                # 更新 Agent 统计
                if current["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents 
                        SET completed_tasks = completed_tasks + 1, 
                            total_tasks = total_tasks + 1,
                            success_rate = (completed_tasks::FLOAT + 1) / NULLIF(total_tasks + 1, 0),
                            status = 'online',
                            current_task_id = NULL,
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        current["assignee_agent"]
                    )
            elif update.status == "failed":
                if current["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents 
                        SET failed_tasks = failed_tasks + 1,
                            total_tasks = total_tasks + 1,
                            success_rate = (completed_tasks::FLOAT) / NULLIF(total_tasks + 1, 0),
                            status = 'online',
                            current_task_id = NULL,
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        current["assignee_agent"]
                    )
        
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
        
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ${param_num} RETURNING *"
        
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


@app.post("/tasks/{task_id}/review")
async def review_task(task_id: int, review: TaskReview, reviewer: str, db=Depends(get_db)):
    """验收任务 - 支持通过、拒绝"""
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task["status"] != "reviewing":
            raise HTTPException(status_code=400, detail=f"Cannot review task with status: {task['status']}")
        
        if review.approved:
            new_status = "completed"
            # 更新 Agent 统计
            if task["assignee_agent"]:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET completed_tasks = completed_tasks + 1,
                        status = 'online',
                        current_task_id = NULL,
                        updated_at = NOW()
                    WHERE name = $1
                    """,
                    task["assignee_agent"]
                )
        else:
            new_status = "rejected"
            # 更新 Agent 统计
            if task["assignee_agent"]:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET failed_tasks = failed_tasks + 1,
                        status = 'online',
                        current_task_id = NULL,
                        updated_at = NOW()
                    WHERE name = $1
                    """,
                    task["assignee_agent"]
                )
        
        await conn.execute(
            """
            UPDATE tasks SET status = $1, feedback = $2, updated_at = NOW(), completed_at = CASE WHEN $1 = 'completed' THEN NOW() ELSE NULL END
            WHERE id = $3
            """,
            new_status, review.feedback, task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "reviewed", task["status"], new_status,
            f"Reviewed by {reviewer}: {'approved' if review.approved else 'rejected'}. Feedback: {review.feedback}",
            reviewer
        )
        
        updated = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    
    return updated


@app.get("/projects/{project_id}/tasks")
async def get_project_tasks(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM tasks WHERE project_id = $1 ORDER BY priority DESC, created_at DESC",
            project_id
        )
    return results


# ============ Agent Endpoints ============

@app.post("/agents/register")
async def register_agent(agent: AgentRegister, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO agents (name, discord_user_id, role, capabilities, skills, status, last_heartbeat)
            VALUES ($1, $2, $3, $4, $5, 'online', NOW())
            ON CONFLICT (name) DO UPDATE SET
                discord_user_id = EXCLUDED.discord_user_id,
                role = EXCLUDED.role,
                capabilities = EXCLUDED.capabilities,
                skills = EXCLUDED.skills,
                status = 'online',
                last_heartbeat = NOW()
            RETURNING *
            """,
            agent.name, agent.discord_user_id, agent.role,
            json.dumps(agent.capabilities) if agent.capabilities else None,
            agent.skills
        )
    return result


@app.post("/agents/{name}/heartbeat")
async def agent_heartbeat(name: str, data: AgentHeartbeat, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE agents SET status = 'online', last_heartbeat = NOW(), current_task_id = $2, updated_at = NOW()
            WHERE name = $1 RETURNING *
            """,
            name, data.current_task_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Agent not found")
    return result


@app.get("/agents")
async def list_agents(status: Optional[str] = None, skill: Optional[str] = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if skill:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE skills @> ARRAY[$1] ORDER BY name",
                skill
            )
        elif status:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE status = $1 ORDER BY name",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM agents ORDER BY name")
    return results


@app.get("/agents/{name}")
async def get_agent(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.delete("/agents/{name}")
async def unregister_agent(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM agents WHERE name = $1", name)
    return {"message": f"Agent {name} unregistered"}


# ============ Dashboard Endpoints ============

@app.get("/dashboard/stats")
async def get_dashboard_stats(db=Depends(get_db)):
    """获取仪表盘统计数据"""
    async with db.acquire() as conn:
        # 项目统计
        project_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active
            FROM projects
            """
        )
        
        # 任务统计
        task_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'assigned') as assigned,
                COUNT(*) FILTER (WHERE status = 'running') as running,
                COUNT(*) FILTER (WHERE status = 'reviewing') as reviewing,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'rejected') as rejected
            FROM tasks
            """
        )
        
        # Agent 统计
        agent_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'online') as online,
                COUNT(*) FILTER (WHERE status = 'offline') as offline,
                COUNT(*) FILTER (WHERE status = 'busy') as busy
            FROM agents
            """
        )
        
        # 最近活动
        recent_logs = await conn.fetch(
            """
            SELECT * FROM task_logs 
            ORDER BY created_at DESC 
            LIMIT 10
            """
        )
    
    return {
        "projects": dict(project_stats),
        "tasks": dict(task_stats),
        "agents": dict(agent_stats),
        "recent_activity": [dict(l) for l in recent_logs]
    }


# ============ Agent Channel Endpoints ============

@app.post("/agent-channels")
async def register_agent_channel(ac: AgentChannel, db=Depends(get_db)):
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", ac.agent_name)
        if not agent:
            await conn.execute(
                """
                INSERT INTO agents (name, role, status, last_heartbeat)
                VALUES ($1, 'unknown', 'online', NOW())
                ON CONFLICT (name) DO NOTHING
                """,
                ac.agent_name
            )
        
        result = await conn.fetchrow(
            """
            INSERT INTO agent_channels (agent_name, channel_id, last_seen)
            VALUES ($1, $2, NOW())
            ON CONFLICT (agent_name, channel_id) 
            DO UPDATE SET last_seen = NOW()
            RETURNING *
            """,
            ac.agent_name, ac.channel_id
        )
    return result


@app.get("/agents/{name}/channels")
async def get_agent_channels(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM agent_channels WHERE agent_name = $1 ORDER BY last_seen DESC",
            name
        )
    return results


@app.get("/channels/{channel_id}/agents")
async def get_channel_agents(channel_id: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT a.* FROM agents a
            JOIN agent_channels ac ON a.name = ac.agent_name
            WHERE ac.channel_id = $1 AND a.status = 'online'
            ORDER BY ac.last_seen DESC
            """,
            channel_id
        )
    return results


@app.delete("/agent-channels")
async def unregister_agent_channel(ac: AgentChannel, db=Depends(get_db)):
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM agent_channels WHERE agent_name = $1 AND channel_id = $2",
            ac.agent_name, ac.channel_id
        )
    return {"message": f"Agent {ac.agent_name} removed from channel {ac.channel_id}"}


# ============ Background Tasks ============

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(heartbeat_monitor())
    asyncio.create_task(stuck_task_monitor())


async def heartbeat_monitor():
    """监控 Agent 心跳，超时设为 offline"""
    while True:
        await asyncio.sleep(60)
        try:
            pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=1)
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET status = 'offline'
                    WHERE status IN ('online', 'busy') 
                    AND last_heartbeat < NOW() - INTERVAL '5 minutes'
                    """
                )
            await pool.close()
        except Exception as e:
            print(f"Heartbeat monitor error: {e}")


async def stuck_task_monitor():
    """监控卡住的任务（running 超过2小时），自动释放"""
    while True:
        await asyncio.sleep(600)  # 每10分钟检查一次
        try:
            pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=1)
            async with pool.acquire() as conn:
                # 找出卡住的任务
                stuck = await conn.fetch(
                    """
                    SELECT * FROM tasks 
                    WHERE status = 'running' 
                    AND started_at < NOW() - INTERVAL '2 hours'
                    """
                )
                
                for task in stuck:
                    print(f"[Monitor] Releasing stuck task: {task['id']} - {task['title']}")
                    
                    # 释放任务
                    await conn.execute(
                        """
                        UPDATE tasks 
                        SET status = 'pending', assignee_agent = NULL, 
                            assigned_at = NULL, started_at = NULL, updated_at = NOW()
                        WHERE id = $1
                        """,
                        task["id"]
                    )
                    
                    # 更新 Agent 状态
                    if task["assignee_agent"]:
                        await conn.execute(
                            """
                            UPDATE agents 
                            SET status = 'online', current_task_id = NULL, updated_at = NOW()
                            WHERE name = $1
                            """,
                            task["assignee_agent"]
                        )
                    
                    # 记录日志
                    await conn.execute(
                        """
                        INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        task["id"], "auto_released", "running", "pending",
                        "Task auto-released due to timeout (2 hours)", "system"
                    )
            await pool.close()
        except Exception as e:
            print(f"Stuck task monitor error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
