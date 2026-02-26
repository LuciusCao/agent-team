"""
Background tasks for monitoring and maintenance
"""

import asyncio
import logging

import asyncpg

from config import Config
from database import get_pool, reset_pool
from utils import update_agent_status_after_task_change

logger = logging.getLogger("task_service")

# 错误计数器，用于控制 reset_pool 频率
_error_counts = {
    "heartbeat": 0,
    "stuck_task": 0
}
_MAX_ERRORS_BEFORE_RESET = 3


def _should_reset_pool(monitor_name: str) -> bool:
    """判断是否应该重置连接池

    使用错误计数器避免频繁重置连接池。
    """
    _error_counts[monitor_name] += 1
    if _error_counts[monitor_name] >= _MAX_ERRORS_BEFORE_RESET:
        _error_counts[monitor_name] = 0
        return True
    return False


def _reset_error_count(monitor_name: str):
    """重置错误计数器（当操作成功时调用）"""
    _error_counts[monitor_name] = 0


async def heartbeat_monitor():
    """监控 Agent 心跳，超时设为 offline"""
    while True:
        await asyncio.sleep(Config.HEARTBEAT_INTERVAL_SECONDS)
        try:
            pool = await get_pool()

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agents
                    SET status = 'offline'
                    WHERE status IN ('online', 'busy')
                    AND last_heartbeat < NOW() - INTERVAL '%s minutes'
                    """ % Config.AGENT_OFFLINE_THRESHOLD_MINUTES
                )

            # 成功执行，重置错误计数
            _reset_error_count("heartbeat")

        except (asyncpg.PostgresError, asyncpg.ConnectionDoesNotExistError, OSError) as e:
            # 数据库相关错误，考虑重置连接池
            logger.error(f"Heartbeat monitor DB error: {e}", exc_info=True)
            if _should_reset_pool("heartbeat"):
                logger.warning("Resetting connection pool due to repeated DB errors")
                await reset_pool()
        except Exception as e:
            # 其他错误，记录但不重置连接池
            logger.error(f"Heartbeat monitor unexpected error: {e}", exc_info=True)


async def stuck_task_monitor():
    """监控卡住的任务，自动释放"""
    while True:
        await asyncio.sleep(Config.STUCK_TASK_CHECK_INTERVAL_SECONDS)
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
                    AND t.deleted_at IS NULL
                    AND t.started_at < NOW() - (
                        COALESCE(
                            t.timeout_minutes,
                            ttd.timeout_minutes,
                            $1
                        ) || ' minutes'
                    )::INTERVAL
                    """,
                    Config.DEFAULT_TASK_TIMEOUT_MINUTES
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

            # 成功执行，重置错误计数
            _reset_error_count("stuck_task")

        except (asyncpg.PostgresError, asyncpg.ConnectionDoesNotExistError, OSError) as e:
            # 数据库相关错误，考虑重置连接池
            logger.error(f"Stuck task monitor DB error: {e}", exc_info=True)
            if _should_reset_pool("stuck_task"):
                logger.warning("Resetting connection pool due to repeated DB errors")
                await reset_pool()
        except Exception as e:
            # 其他错误，记录但不重置连接池
            logger.error(f"Stuck task monitor unexpected error: {e}", exc_info=True)


async def soft_delete_cleanup_monitor():
    """定期清理超过保留期的软删除记录"""
    CLEANUP_INTERVAL_SECONDS = 86400  # 每天运行一次
    RETENTION_DAYS = 30  # 保留30天

    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            from utils import cleanup_soft_deleted

            pool = await get_pool()

            async with pool.acquire() as conn:
                total_cleaned = 0
                for table in ['tasks', 'agents', 'projects']:
                    count = await cleanup_soft_deleted(conn, table, RETENTION_DAYS)
                    total_cleaned += count

                if total_cleaned > 0:
                    logger.info(
                        f"Soft delete cleanup completed: {total_cleaned} records permanently deleted",
                        extra={"action": "soft_delete_cleanup", "total_cleaned": total_cleaned}
                    )

            _reset_error_count("soft_delete_cleanup")

        except (asyncpg.PostgresError, asyncpg.ConnectionDoesNotExistError, OSError) as e:
            logger.error(f"Soft delete cleanup DB error: {e}", exc_info=True)
            if _should_reset_pool("soft_delete_cleanup"):
                await reset_pool()
        except Exception as e:
            logger.error(f"Soft delete cleanup unexpected error: {e}", exc_info=True)
