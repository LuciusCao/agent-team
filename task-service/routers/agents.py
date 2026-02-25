"""
Agent API Router
"""

import json

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from models import AgentHeartbeat, AgentRegister
from security import rate_limit, verify_api_key
from utils import hard_delete, restore_soft_deleted, soft_delete

router = APIRouter()


@router.post("/register/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
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
                last_heartbeat = NOW(),
                deleted_at = NULL
            RETURNING *
            """,
            agent.name, agent.discord_user_id, agent.role,
            json.dumps(agent.capabilities) if agent.capabilities else None,
            agent.skills
        )
    return result


@router.post("/{name}/heartbeat/", dependencies=[Depends(rate_limit)])
async def agent_heartbeat(name: str, data: AgentHeartbeat, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE agents SET status = 'online', last_heartbeat = NOW(), current_task_id = $2, updated_at = NOW()
            WHERE name = $1 AND deleted_at IS NULL
            RETURNING *
            """,
            name, data.current_task_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Agent not found")
    return result


@router.get("/", dependencies=[Depends(rate_limit)])
async def list_agents(status: str | None = None, skill: str | None = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if skill:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE skills @> ARRAY[$1] AND deleted_at IS NULL ORDER BY name",
                skill
            )
        elif status:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE status = $1 AND deleted_at IS NULL ORDER BY name",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM agents WHERE deleted_at IS NULL ORDER BY name")
    return results


@router.get("/{name}", dependencies=[Depends(rate_limit)])
async def get_agent(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1 AND deleted_at IS NULL", name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{name}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def unregister_agent(name: str, hard: bool = False, db=Depends(get_db)):
    """注销 Agent（默认软删除，hard=true 时物理删除）"""
    async with db.acquire() as conn:
        if hard:
            success = await hard_delete(conn, "agents", name, id_column="name")
        else:
            success = await soft_delete(conn, "agents", name, id_column="name")

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found or already deleted")

    return {"message": f"Agent {name} {'hard ' if hard else ''}unregistered successfully"}


@router.post("/{name}/restore", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def restore_agent(name: str, db=Depends(get_db)):
    """恢复软删除的 Agent"""
    async with db.acquire() as conn:
        success = await restore_soft_deleted(conn, "agents", name, id_column="name")

    if not success:
        raise HTTPException(status_code=404, detail="Agent not found or not deleted")

    return {"message": f"Agent {name} restored successfully"}


@router.get("/{name}/channels/", dependencies=[Depends(rate_limit)])
async def get_agent_channels(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM agent_channels WHERE agent_name = $1 ORDER BY last_seen DESC",
            name
        )
    return results
