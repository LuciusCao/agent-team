"""
Background tasks for monitoring and maintenance
"""

import os
import asyncio
import logging
from datetime import datetime

import asyncpg
from database import get_pool, reset_pool, DB_URL
from utils import update_agent_status_after_task_change

logger = logging.getLogger("task_service")

_pool_lock = asyncio.Lock()


async def heartbeat_monitor():
    """监控 Agent 心跳，超时设为 offline"""
    global _pool
    while True:
        await asyncio.sleep(60)
        try:
            pool = await get_pool()
            
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET status = 'offline'
                    WHERE status IN ('online', 'busy') 
                    AND last_heartbeat < NOW() - INTERVAL '5 minutes'
                    """
                )
        except Exception as e:
            logger.error(f"Heartbeat monitor error: {e}", exc_info=True)
            await reset_pool()


async def stuck_task_monitor():
    """监控卡住的任务，自动释放"""
    DEFAULT_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_TASK_TIMEOUT_MINUTES", "120"))
    
    while True:
        await asyncio.sleep(600)  # 每10分钟检查一次
        try:
            pool = await get_pool()
            
            async with pool.acquire() as conn:
                stuck = await conn.fetch(
                    """
                    SELECT 
                        t.*,
                        COALESCE(
                            t.timeout_minutes,
                            ttd.timeout_minutes,
                            $1
                        ) as effective_timeout_minutes
                    FROM tasks t
                    LEFT JOIN task_type_defaults ttd ON t.task_type = ttd.task_type
                    WHERE t.status = 'running'
                    AND t.started_at < NOW() - (
                        COALESCE(
                            t.timeout_minutes,
                            ttd.timeout_minutes,
                            $1
                        ) || ' minutes'
                    )::INTERVAL
                    """,
                    DEFAULT_TIMEOUT_MINUTES
                )
                
                for task in stuck:
                    timeout = task['effective_timeout_minutes']
                    logger.warning(
                        f"Task {task['id']} timed out after {timeout} minutes",
                        extra={
                            "task_id": task["id"],
                            "task_title": task["title"],
                            "agent_name": task["assignee_agent"],
                            "timeout_minutes": timeout,
                            "action": "auto_release_timeout"
                        }
                    )
                    
                    await conn.execute(
                        """
                        UPDATE tasks 
                        SET status = 'pending', assignee_agent = NULL, 
                            assigned_at = NULL, started_at = NULL, updated_at = NOW()
                        WHERE id = $1
                        """,
                        task["id"]
                    )
                    
                    if task["assignee_agent"]:
                        await update_agent_status_after_task_change(conn, task["assignee_agent"])
                    
                    await conn.execute(
                        """
                        INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        task["id"], "auto_released", "running", "pending",
                        f"Task auto-released due to timeout ({timeout} minutes)", "system"
                    )
        except Exception as e:
            logger.error(
                "Stuck task monitor error",
                exc_info=True,
                extra={"action": "stuck_task_monitor_error"}
            )
            await reset_pool()
