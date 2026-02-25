"""
Database connection management
"""

import asyncio

import asyncpg

from config import Config

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _create_pool() -> asyncpg.Pool:
    """创建数据库连接池

    包含完整的超时和连接管理配置。
    """
    return await asyncpg.create_pool(
        Config.DATABASE_URL,
        min_size=Config.DB_POOL_MIN_SIZE,
        max_size=Config.DB_POOL_MAX_SIZE,
        command_timeout=Config.DB_COMMAND_TIMEOUT,
        max_queries=Config.DB_MAX_QUERIES,
        timeout=10,  # 连接建立超时（秒）
        server_settings={
            'application_name': 'task-service',
            'jit': 'off',  # 禁用 JIT 以避免某些兼容性问题
        }
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
