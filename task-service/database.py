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


async def get_db():
    """获取数据库连接池

    使用双检锁确保连接池只被创建一次
    """
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return _pool


async def get_pool():
    """获取全局连接池（用于后台任务）"""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return _pool


async def reset_pool():
    """重置连接池（用于错误恢复）"""
    global _pool
    async with _pool_lock:
        _pool = None
