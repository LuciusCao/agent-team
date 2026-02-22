#!/usr/bin/env python3
"""
Task Management Service
FastAPI + PostgreSQL
"""

import os
import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import asyncpg

app = FastAPI(title="Task Management Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/taskmanager")

pool: Optional[asyncpg.Pool] = None


async def get_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return pool


# Pydantic models

## Agent
class AgentRegister(BaseModel):
    name: str
    discord_user_id: Optional[str] = None
    role: str  # research, copywrite, video, coordinator
    capabilities: Optional[dict] = None


class AgentHeartbeat(BaseModel):
    name: str


class AgentChannel(BaseModel):
    """Agent 在某频道活跃的记录"""
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
    assignee_agent: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_mention: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    parent_task_id: Optional[int] = None
    dependencies: Optional[List[int]] = None
    created_by: Optional[str] = None
    due_at: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict] = None
    assignee_agent: Optional[str] = None


class TaskReview(BaseModel):
    approved: bool
    feedback: Optional[str] = None


# API Routes
@app.get("/")
async def root():
    return {"status": "ok", "service": "task-management"}


@app.post("/projects")
async def create_project(project: ProjectCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO projects (name, discord_channel_id, description)
            VALUES ($1, $2, $3)
            RETURNING id, name, discord_channel_id, description, created_at
            """,
            project.name, project.discord_channel_id, project.description
        )
    return result


@app.get("/projects")
async def list_projects(db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch("SELECT * FROM projects ORDER BY created_at DESC")
    return results


@app.get("/projects/{project_id}")
async def get_project(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/tasks")
async def create_task(task: TaskCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type,
                assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                parent_task_id, dependencies, created_by, due_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            task.project_id, task.title, task.description, task.task_type,
            task.assignee_agent, task.reviewer_id, task.reviewer_mention,
            task.acceptance_criteria, task.parent_task_id,
            task.dependencies, task.created_by, task.due_at
        )
        
        # Log the creation
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
    db=Depends(get_db)
):
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    
    if project_id:
        params.append(project_id)
        query += f" AND project_id = ${len(params)}"
    if status:
        params.append(status)
        query += f" AND status = ${len(params)}"
    if assignee:
        params.append(assignee)
        query += f" AND assignee_agent = ${len(params)}"
    
    query += " ORDER BY created_at DESC"
    
    async with db.acquire() as conn:
        results = await conn.fetch(query, *params)
    return results


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
        # Get current task
        current = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not current:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Build update query
        updates = []
        params = []
        param_num = 1
        
        if update.status is not None:
            updates.append(f"status = ${param_num}")
            params.append(update.status)
            param_num += 1
            
            # Update completed_at if completing
            if update.status == "completed":
                updates.append("completed_at = NOW()")
        
        if update.result is not None:
            updates.append(f"result = ${param_num}")
            params.append(json.dumps(update.result))
            param_num += 1
        
        if update.assignee_agent is not None:
            updates.append(f"assignee_agent = ${param_num}")
            params.append(update.assignee_agent)
            param_num += 1
        
        if not updates:
            return current
        
        updates.append("updated_at = NOW()")
        params.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ${param_num} RETURNING *"
        
        result = await conn.fetchrow(query, *params)
        
        # Log the update
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
async def review_task(task_id: int, review: TaskReview, db=Depends(get_db)):
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if review.approved:
            new_status = "completed"
        else:
            new_status = "running"
        
        await conn.execute(
            "UPDATE tasks SET status = $1, feedback = $2, updated_at = NOW() WHERE id = $3",
            new_status, review.feedback, task_id
        )
        
        # Log the review
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message)
            VALUES ($1, $2, $3, $4, $5)
            """,
            task_id, "reviewed", task["status"], new_status,
            f"Reviewed: {'approved' if review.approved else 'rejected'}. Feedback: {review.feedback}"
        )
        
        updated = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    
    return updated


@app.get("/projects/{project_id}/tasks")
async def get_project_tasks(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM tasks WHERE project_id = $1 ORDER BY created_at DESC",
            project_id
        )
    return results


# ============ Agent Endpoints ============

@app.post("/agents/register")
async def register_agent(agent: AgentRegister, db=Depends(get_db)):
    """注册 Agent"""
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO agents (name, discord_user_id, role, capabilities, status, last_heartbeat)
            VALUES ($1, $2, $3, $4, 'online', NOW())
            ON CONFLICT (name) DO UPDATE SET
                discord_user_id = EXCLUDED.discord_user_id,
                role = EXCLUDED.role,
                capabilities = EXCLUDED.capabilities,
                status = 'online',
                last_heartbeat = NOW()
            RETURNING *
            """,
            agent.name, agent.discord_user_id, agent.role,
            json.dumps(agent.capabilities) if agent.capabilities else None
        )
    return result


@app.post("/agents/{name}/heartbeat")
async def agent_heartbeat(name: str, db=Depends(get_db)):
    """Agent 心跳"""
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE agents SET status = 'online', last_heartbeat = NOW()
            WHERE name = $1 RETURNING *
            """,
            name
        )
        if not result:
            raise HTTPException(status_code=404, detail="Agent not found")
    return result


@app.get("/agents")
async def list_agents(status: Optional[str] = None, db=Depends(get_db)):
    """列出可用 Agent"""
    async with db.acquire() as conn:
        if status:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE status = $1 ORDER BY name",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM agents ORDER BY name")
    return results


@app.get("/agents/{name}")
async def get_agent(name: str, db=Depends(get_db)):
    """获取 Agent 详情"""
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.delete("/agents/{name}")
async def unregister_agent(name: str, db=Depends(get_db)):
    """注销 Agent"""
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM agents WHERE name = $1", name)
    return {"message": f"Agent {name} unregistered"}


# ============ Agent Channel Endpoints ============

@app.post("/agent-channels")
async def register_agent_channel(ac: AgentChannel, db=Depends(get_db)):
    """记录 Agent 在某频道活跃"""
    async with db.acquire() as conn:
        # 先确保 agent 存在
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", ac.agent_name)
        if not agent:
            # 自动注册 agent
            await conn.execute(
                """
                INSERT INTO agents (name, role, status, last_heartbeat)
                VALUES ($1, 'unknown', 'online', NOW())
                ON CONFLICT (name) DO NOTHING
                """,
                ac.agent_name
            )
        
        # 记录频道活跃
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
    """查询 Agent 活跃的所有频道"""
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM agent_channels WHERE agent_name = $1 ORDER BY last_seen DESC",
            name
        )
    return results


@app.get("/channels/{channel_id}/agents")
async def get_channel_agents(channel_id: str, db=Depends(get_db)):
    """查询某频道的所有活跃 Agent"""
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
    """移除 Agent 在某频道的活跃状态"""
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM agent_channels WHERE agent_name = $1 AND channel_id = $2",
            ac.agent_name, ac.channel_id
        )
    return {"message": f"Agent {ac.agent_name} removed from channel {ac.channel_id}"}


# ============ Background Tasks ============

import asyncio

@app.on_event("startup")
async def startup_event():
    """启动后台任务"""
    asyncio.create_task(heartbeat_monitor())


async def heartbeat_monitor():
    """监控 Agent 心跳，超时设为 offline"""
    while True:
        await asyncio.sleep(60)  # 每分钟检查一次
        try:
            pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=1)
            async with pool.acquire() as conn:
                # 将 5 分钟没有心跳的 Agent 设为 offline
                await conn.execute(
                    """
                    UPDATE agents 
                    SET status = 'offline'
                    WHERE status = 'online' 
                    AND last_heartbeat < NOW() - INTERVAL '5 minutes'
                    """
                )
            await pool.close()
        except Exception as e:
            print(f"Heartbeat monitor error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
