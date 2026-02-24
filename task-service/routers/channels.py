"""
Channels API Router
"""

from fastapi import APIRouter, Depends

from database import get_db
from security import verify_api_key, rate_limit
from models import AgentChannel

router = APIRouter()
channels_router = APIRouter()


@router.post("/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
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


@router.delete("/", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def unregister_agent_channel(ac: AgentChannel, db=Depends(get_db)):
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM agent_channels WHERE agent_name = $1 AND channel_id = $2",
            ac.agent_name, ac.channel_id
        )
    return {"message": f"Agent {ac.agent_name} removed from channel {ac.channel_id}"}


@channels_router.get("/{channel_id}/agents", dependencies=[Depends(rate_limit)])
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
