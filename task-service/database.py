"""
Database connection management
"""

import os
import asyncpg
import asyncio
from typing import Optional

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/taskmanager")
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()

# Connection pool settings
POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
POOL_COMMAND_TIMEOUT = int(os.getenv("DB_COMMAND_TIMEOUT", "60"))
POOL_MAX_INACTIVE_TIME = int(os.getenv("DB_MAX_INACTIVE_TIME", "300"))
POOL_MAX_QUERIES = int(os.getenv("DB_MAX_QUERIES", "100000"))


async def _create_pool() -> asyncpg.Pool:
    """创建数据库连接池
    
    包含完整的超时和连接管理配置。
    """
    return await asyncpg.create_pool(
        DB_URL,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        command_timeout=POOL_COMMAND_TIMEOUT,
        max_inactive_time=POOL_MAX_INACTIVE_TIME,
        max_queries=POOL_MAX_QUERIES,
    )


async def get_db():
    """获取数据库连接池

    使用双检锁确保连接池只被创建一次
    """
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await _create_pool()
    return _pool


async def get_pool():
    """获取全局连接池（用于后台任务）"""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await _create_pool()
    return _pool


async def reset_pool():
    """重置连接池（用于错误恢复）"""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass  # 忽略关闭时的错误
        _pool = None
