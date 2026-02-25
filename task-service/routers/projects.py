"""
Project API Router
"""


from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models import ProjectCreate, TaskCreate
from security import rate_limit, verify_api_key
from utils import hard_delete, restore_soft_deleted, soft_delete, validate_task_dependencies

router = APIRouter()


@router.post("/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
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


@router.get("/", dependencies=[Depends(rate_limit)])
async def list_projects(status: str | None = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if status:
            results = await conn.fetch(
                "SELECT * FROM projects WHERE status = $1 AND deleted_at IS NULL ORDER BY created_at DESC",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY created_at DESC")
    return results


@router.get("/{project_id}", dependencies=[Depends(rate_limit)])
async def get_project(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1 AND deleted_at IS NULL", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/progress", dependencies=[Depends(rate_limit)])
async def get_project_progress(project_id: int, db=Depends(get_db)):
    """获取项目进度统计"""
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1 AND deleted_at IS NULL", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

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
            FROM tasks WHERE project_id = $1 AND deleted_at IS NULL
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


@router.post("/{project_id}/breakdown", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def breakdown_project(project_id: int, tasks: list[TaskCreate], db=Depends(get_db)):
    """项目拆分：批量创建任务"""
    validate_task_dependencies(tasks)

    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1 AND deleted_at IS NULL", project_id)
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

            await conn.execute(
                "INSERT INTO task_logs (task_id, action, message, actor) VALUES ($1, $2, $3, $4)",
                result["id"], "created", f"Task created via breakdown: {task.title}", task.created_by or "system"
            )

            created_tasks.append(dict(result))

    return {"project_id": project_id, "tasks_created": len(created_tasks), "tasks": created_tasks}


@router.get("/{project_id}/tasks", dependencies=[Depends(rate_limit)])
async def get_project_tasks(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM tasks WHERE project_id = $1 AND deleted_at IS NULL ORDER BY priority DESC, created_at DESC",
            project_id
        )
    return results


@router.delete("/{project_id}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def delete_project(project_id: int, hard: bool = False, db=Depends(get_db)):
    """删除项目（默认软删除，hard=true 时物理删除）"""
    async with db.acquire() as conn:
        if hard:
            success = await hard_delete(conn, "projects", project_id)
        else:
            success = await soft_delete(conn, "projects", project_id)

    if not success:
        raise HTTPException(status_code=404, detail="Project not found or already deleted")

    return {"message": f"Project {project_id} {'hard ' if hard else ''}deleted successfully"}


@router.post("/{project_id}/restore", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def restore_project(project_id: int, db=Depends(get_db)):
    """恢复软删除的项目"""
    async with db.acquire() as conn:
        success = await restore_soft_deleted(conn, "projects", project_id)

    if not success:
        raise HTTPException(status_code=404, detail="Project not found or not deleted")

    return {"message": f"Project {project_id} restored successfully"}
