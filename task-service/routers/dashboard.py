"""
Dashboard API Router
"""

from fastapi import APIRouter, Depends

from database import get_db
from security import rate_limit

router = APIRouter()


@router.get("/stats", dependencies=[Depends(rate_limit)])
async def get_dashboard_stats(db=Depends(get_db)):
    """获取仪表盘统计数据"""
    async with db.acquire() as conn:
        project_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active
            FROM projects
            """
        )
        
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
