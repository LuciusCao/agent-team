"""
Task Service 通用工具函数
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from functools import wraps

import asyncpg

from config import Config

logger = logging.getLogger("task_service")


# ============ Logging Setup ============

def setup_logging():
    """配置结构化日志

    设置根日志记录器和 uvicorn 的日志格式
    """
    from config import Config
    logger = logging.getLogger("task_service")
    logger.setLevel(Config.LOG_LEVEL.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.handlers = [handler]

    # 配置 uvicorn 日志
    logging.getLogger("uvicorn").handlers = [handler]
    logging.getLogger("uvicorn.access").handlers = [handler]

    return logger

class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, "agent_name"):
            log_obj["agent_name"] = record.agent_name
        if hasattr(record, "task_id"):
            log_obj["task_id"] = record.task_id
        if hasattr(record, "project_id"):
            log_obj["project_id"] = record.project_id
        if hasattr(record, "action"):
            log_obj["action"] = record.action
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "extra"):
            log_obj.update(record.extra)

        # 添加异常信息
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


# ============ Database Utilities ============

def retry_on_db_error(max_retries=3, base_delay=1):
    """数据库操作重试装饰器
    
    使用指数退避策略重试数据库操作。
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.PostgresError, asyncpg.ConnectionDoesNotExistError, OSError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # 指数退避
                        logger.warning(
                            f"DB operation failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}",
                            extra={"action": "db_retry", "attempt": attempt + 1, "delay": delay}
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"DB operation failed after {max_retries} attempts: {e}",
                            extra={"action": "db_retry_exhausted", "max_retries": max_retries}
                        )
            raise last_exception
        return wrapper
    return decorator


async def check_idempotency(conn: asyncpg.Connection, idempotency_key: str | None = None):
    """检查幂等性（数据库持久化版本）
    
    如果提供了幂等键且已存在（未过期），返回缓存的响应。
    否则返回 None，表示需要执行操作。
    
    注意：不过期键的清理交给后台任务或数据库定时任务处理，
    避免在检查路径上引入竞态条件。
    
    Args:
        conn: 数据库连接
        idempotency_key: 幂等键（通常由客户端生成 UUID）
    
    Returns:
        tuple: (cached_response, should_skip)
    """
    if not idempotency_key:
        return None, False

    # 检查幂等键是否存在且未过期（24小时内）
    # 不在此处清理过期键，避免竞态条件
    row = await conn.fetchrow(
        """SELECT response FROM idempotency_keys 
           WHERE key = $1 
           AND created_at > NOW() - INTERVAL '24 hours'""",
        idempotency_key
    )

    if row:
        cached_response = json.loads(row['response'])
        logger.info(
            f"Idempotency hit for key: {idempotency_key}",
            extra={"idempotency_key": idempotency_key, "action": "idempotency_hit"}
        )
        return cached_response, True

    return None, False


async def cleanup_expired_idempotency_keys(conn: asyncpg.Connection) -> int:
    """清理过期的幂等性键
    
    应该在后台任务中定期调用，而不是在检查路径上。
    
    Args:
        conn: 数据库连接
    
    Returns:
        int: 清理的键数量
    """
    result = await conn.execute(
        "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours'"
    )
    # 解析结果，格式类似 "DELETE 10"
    try:
        count = int(result.split()[1]) if result.split() else 0
    except (IndexError, ValueError):
        count = 0

    if count > 0:
        logger.info(
            f"Cleaned up {count} expired idempotency keys",
            extra={"action": "idempotency_cleanup", "count": count}
        )
    return count


async def store_idempotency_response(conn: asyncpg.Connection, idempotency_key: str | None, response: dict):
    """存储幂等响应（数据库持久化版本）
    
    Args:
        conn: 数据库连接
        idempotency_key: 幂等键
        response: 响应数据
    """
    if idempotency_key:
        await conn.execute(
            """
            INSERT INTO idempotency_keys (key, response, created_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO NOTHING
            """,
            idempotency_key, json.dumps(response)
        )
        logger.debug(
            f"Stored idempotency response for key: {idempotency_key}",
            extra={"idempotency_key": idempotency_key, "action": "idempotency_store"}
        )


# ============ Task Utilities ============

async def check_dependencies(conn: asyncpg.Connection, task_id: int, for_update: bool = False) -> tuple[bool, list]:
    """检查任务依赖是否完成

    Args:
        conn: 数据库连接
        task_id: 任务ID
        for_update: 是否使用 FOR UPDATE 锁定依赖任务（用于写操作）

    Returns:
        tuple: (所有依赖完成, 依赖列表)
    """
    task = await conn.fetchrow("SELECT dependencies FROM tasks WHERE id = $1", task_id)
    if not task or not task["dependencies"]:
        return True, []

    deps = task["dependencies"]

    # 检查所有依赖任务是否完成
    for dep_id in deps:
        if for_update:
            # 使用 FOR UPDATE 锁定依赖任务，防止竞态条件
            dep = await conn.fetchrow(
                "SELECT status FROM tasks WHERE id = $1 FOR UPDATE",
                dep_id
            )
        else:
            dep = await conn.fetchrow(
                "SELECT status FROM tasks WHERE id = $1",
                dep_id
            )
        if not dep or dep["status"] != "completed":
            return False, deps

    return True, []


def validate_task_dependencies(tasks: list) -> None:
    """验证任务依赖关系，检测循环依赖

    Args:
        tasks: 任务列表

    Raises:
        HTTPException: 如果检测到循环依赖或无效依赖
    """
    from collections import defaultdict, deque

    from fastapi import HTTPException

    n = len(tasks)
    graph = defaultdict(list)
    in_degree = [0] * n

    for i, task in enumerate(tasks):
        if task.dependencies:
            for dep_idx in task.dependencies:
                if dep_idx < 0 or dep_idx >= n:
                    raise HTTPException(status_code=400, detail=f"Invalid dependency index: {dep_idx}")
                if dep_idx == i:
                    raise HTTPException(status_code=400, detail="Task cannot depend on itself")
                graph[dep_idx].append(i)
                in_degree[i] += 1

    queue = deque([i for i in range(n) if in_degree[i] == 0])
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != n:
        raise HTTPException(status_code=400, detail="Circular dependency detected")


def validate_task_dependencies_for_create(dependencies: list[int]) -> None:
    """验证单个任务的依赖关系

    用于 create_task 时检查依赖列表是否有效。
    注意：这里只能检查基础的有效性，无法检查循环依赖
    （因为循环依赖需要知道所有相关任务）。

    Args:
        dependencies: 依赖任务ID列表

    Raises:
        HTTPException: 如果依赖列表无效
    """
    from fastapi import HTTPException

    if not dependencies:
        return

    # 检查是否有重复依赖
    if len(dependencies) != len(set(dependencies)):
        raise HTTPException(status_code=400, detail="Duplicate dependencies detected")

    # 检查是否有负数或零
    for dep_id in dependencies:
        if dep_id <= 0:
            raise HTTPException(status_code=400, detail=f"Invalid dependency ID: {dep_id}")


async def check_circular_dependency(conn: asyncpg.Connection, task_id: int | None, new_deps: list[int]) -> bool:
    """检查添加新依赖是否会形成循环

    使用 BFS 遍历依赖图，检测是否会回到当前任务。

    Args:
        conn: 数据库连接
        task_id: 当前任务ID（新建任务时为 None）
        new_deps: 新依赖的任务ID列表

    Returns:
        bool: 如果会形成循环返回 True
    """
    if not new_deps:
        return False

    visited = set()
    queue = list(new_deps)

    while queue:
        dep_id = queue.pop(0)

        # 如果依赖指向当前任务，形成循环
        if task_id is not None and dep_id == task_id:
            return True

        if dep_id in visited:
            continue
        visited.add(dep_id)

        # 查询该任务的依赖
        try:
            row = await conn.fetchrow(
                "SELECT dependencies FROM tasks WHERE id = $1 AND deleted_at IS NULL",
                dep_id
            )
            if row and row['dependencies']:
                queue.extend(row['dependencies'])
        except Exception:
            # 如果查询失败（如任务不存在），继续检查其他依赖
            pass

    return False


# ============ Agent Utilities ============

async def update_agent_status_after_task_change(conn: asyncpg.Connection, agent_name: str):
    """任务变更后更新 Agent 状态
    
    检查 Agent 是否还有其他进行中的任务：
    - 如果没有，设为 online，current_task_id = NULL
    - 如果有，设为 busy，current_task_id = 其中一个任务ID
    
    Args:
        conn: 数据库连接
        agent_name: Agent 名称
    """
    # 检查是否还有其他进行中的任务
    other_tasks = await conn.fetchrow(
        """
        SELECT COUNT(*) as count, 
               MIN(id) as next_task_id
        FROM tasks 
        WHERE assignee_agent = $1 
        AND status IN ('assigned', 'running', 'reviewing')
        """,
        agent_name
    )

    if other_tasks['count'] == 0:
        # 没有其他任务了，设为 online
        await conn.execute(
            """
            UPDATE agents 
            SET status = 'online', current_task_id = NULL, updated_at = NOW()
            WHERE name = $1
            """,
            agent_name
        )
    else:
        # 还有其他任务，设为 busy，更新 current_task_id
        await conn.execute(
            """
            UPDATE agents 
            SET status = 'busy', current_task_id = $1, updated_at = NOW()
            WHERE name = $2
            """,
            other_tasks['next_task_id'], agent_name
        )


async def update_agent_stats_on_completion(conn: asyncpg.Connection, agent_name: str, success: bool = True):
    """更新 Agent 统计信息
    
    Args:
        conn: 数据库连接
        agent_name: Agent 名称
        success: 是否成功完成
    """
    if success:
        await conn.execute(
            """
            UPDATE agents 
            SET completed_tasks = completed_tasks + 1, 
                total_tasks = total_tasks + 1,
                success_rate = (completed_tasks::FLOAT + 1) / NULLIF(total_tasks + 1, 0),
                updated_at = NOW()
            WHERE name = $1
            """,
            agent_name
        )
    else:
        await conn.execute(
            """
            UPDATE agents 
            SET failed_tasks = failed_tasks + 1,
                total_tasks = total_tasks + 1,
                success_rate = (completed_tasks::FLOAT) / NULLIF(total_tasks + 1, 0),
                updated_at = NOW()
            WHERE name = $1
            """,
            agent_name
        )


# ============ Logging Utilities ============

async def log_task_action(
    conn: asyncpg.Connection,
    task_id: int,
    action: str,
    old_status: str | None = None,
    new_status: str | None = None,
    message: str = "",
    actor: str = "system"
):
    """记录任务操作日志
    
    Args:
        conn: 数据库连接
        task_id: 任务ID
        action: 操作类型
        old_status: 原状态
        new_status: 新状态
        message: 消息
        actor: 执行者
    """
    await conn.execute(
        """
        INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        task_id, action, old_status, new_status, message, actor
    )


def log_structured(level: str, message: str, **kwargs):
    """记录结构化日志
    
    Args:
        level: 日志级别 (debug, info, warning, error)
        message: 日志消息
        **kwargs: 额外字段
    """
    extra = {"action": kwargs.pop("action", "unknown")}
    extra.update(kwargs)

    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=extra)


# ============ Rate Limiting Utilities ============

class RateLimiter:
    """简单的内存速率限制器

    注意：生产环境建议使用 Redis 实现分布式限流
    """

    def __init__(self, window: int = 60, max_requests: int = 100, max_store_size: int = 10000):
        self.window = window
        self.max_requests = max_requests
        self.max_store_size = max_store_size
        self.store = {}
        self._last_cleanup_time = 0
        self._lock = asyncio.Lock()  # 添加锁保证线程安全

    async def _cleanup_if_needed(self, current_time: float) -> None:
        """定期清理过期记录，防止内存泄漏"""
        if len(self.store) < self.max_store_size and current_time - self._last_cleanup_time < self.window:
            return

        expired_threshold = current_time - self.window
        expired_keys = [
            key for key, timestamps in self.store.items()
            if not timestamps or all(ts < expired_threshold for ts in timestamps)
        ]

        for key in expired_keys:
            del self.store[key]

        self._last_cleanup_time = current_time

    async def is_allowed(self, key: str) -> bool:
        """检查是否允许请求

        Args:
            key: 限制键（通常是客户端IP）

        Returns:
            bool: 是否允许
        """
        async with self._lock:
            current_time = datetime.now().timestamp()

            # 定期清理过期记录
            await self._cleanup_if_needed(current_time)

            # 检查存储上限，防止内存无限增长
            if len(self.store) >= self.max_store_size:
                # 强制清理一半最老的记录
                await self._force_cleanup_oldest()

            # 清理过期记录
            if key in self.store:
                self.store[key] = [
                    ts for ts in self.store[key]
                    if current_time - ts < self.window
                ]
            else:
                self.store[key] = []

            # 检查是否超过限制
            if len(self.store[key]) >= self.max_requests:
                return False

            # 记录本次请求
            self.store[key].append(current_time)
            return True

    async def _force_cleanup_oldest(self) -> None:
        """强制清理最老的记录（当达到存储上限时）"""
        # 按最后访问时间排序，清理一半
        sorted_keys = sorted(
            self.store.keys(),
            key=lambda k: max(self.store[k]) if self.store[k] else 0
        )
        keys_to_remove = sorted_keys[:len(sorted_keys) // 2]
        for key in keys_to_remove:
            del self.store[key]
        logger.warning(
            f"RateLimiter force cleanup: removed {len(keys_to_remove)} keys",
            extra={"action": "rate_limiter_force_cleanup", "removed": len(keys_to_remove)}
        )

    async def get_remaining(self, key: str) -> int:
        """获取剩余请求数

        Args:
            key: 限制键

        Returns:
            int: 剩余请求数
        """
        async with self._lock:
            current_time = datetime.now().timestamp()

            if key not in self.store:
                return self.max_requests

            # 清理过期记录
            valid_requests = [
                ts for ts in self.store[key]
                if current_time - ts < self.window
            ]

            return max(0, self.max_requests - len(valid_requests))


# ============ Validation Utilities ============

def validate_task_type(task_type: str) -> bool:
    """验证任务类型是否有效
    
    Args:
        task_type: 任务类型
    
    Returns:
        bool: 是否有效
    """
    valid_types = {
        'research', 'copywrite', 'video', 'review', 'publish',
        'analysis', 'design', 'development', 'testing', 'deployment', 'coordination'
    }
    return task_type in valid_types


def validate_agent_role(role: str) -> bool:
    """验证 Agent 角色是否有效
    
    Args:
        role: 角色
    
    Returns:
        bool: 是否有效
    """
    valid_roles = {
        'research', 'copywrite', 'video', 'coordinator', 'reviewer',
        'developer', 'designer', 'tester', 'project_manager'
    }
    return role in valid_roles


def sanitize_string(value: str | None, max_length: int = 255) -> str | None:
    """清理字符串输入
    
    Args:
        value: 输入字符串
        max_length: 最大长度
    
    Returns:
        Optional[str]: 清理后的字符串
    """
    if value is None:
        return None

    # 去除首尾空白
    value = value.strip()

    # 截断过长字符串
    if len(value) > max_length:
        value = value[:max_length]

    return value


# ============ Soft Delete Utilities ============

SOFT_DELETE_TABLES = {'tasks', 'agents', 'projects'}


async def soft_delete(conn: asyncpg.Connection, table: str, id_value: int, id_column: str = 'id') -> bool:
    """软删除记录

    Args:
        conn: 数据库连接
        table: 表名
        id_value: 记录ID
        id_column: ID列名，默认为 'id'

    Returns:
        bool: 是否成功删除

    Raises:
        ValueError: 如果表名不在允许列表中
    """
    if table not in SOFT_DELETE_TABLES:
        raise ValueError(f"Table {table} does not support soft delete")

    result = await conn.execute(
        f"""
        UPDATE {table}
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE {id_column} = $1 AND deleted_at IS NULL
        """,
        id_value
    )

    # 解析结果，格式类似 "UPDATE 1"
    try:
        count = int(result.split()[1]) if result.split() else 0
    except (IndexError, ValueError):
        count = 0

    return count > 0


async def restore_soft_deleted(conn: asyncpg.Connection, table: str, id_value: int, id_column: str = 'id') -> bool:
    """恢复软删除的记录

    Args:
        conn: 数据库连接
        table: 表名
        id_value: 记录ID
        id_column: ID列名，默认为 'id'

    Returns:
        bool: 是否成功恢复

    Raises:
        ValueError: 如果表名不在允许列表中
    """
    if table not in SOFT_DELETE_TABLES:
        raise ValueError(f"Table {table} does not support soft delete")

    result = await conn.execute(
        f"""
        UPDATE {table}
        SET deleted_at = NULL, updated_at = NOW()
        WHERE {id_column} = $1 AND deleted_at IS NOT NULL
        """,
        id_value
    )

    try:
        count = int(result.split()[1]) if result.split() else 0
    except (IndexError, ValueError):
        count = 0

    return count > 0


async def hard_delete(conn: asyncpg.Connection, table: str, id_value: int, id_column: str = 'id') -> bool:
    """物理删除记录（谨慎使用）

    Args:
        conn: 数据库连接
        table: 表名
        id_value: 记录ID
        id_column: ID列名，默认为 'id'

    Returns:
        bool: 是否成功删除
    """
    result = await conn.execute(
        f"DELETE FROM {table} WHERE {id_column} = $1",
        id_value
    )

    try:
        count = int(result.split()[1]) if result.split() else 0
    except (IndexError, ValueError):
        count = 0

    return count > 0


async def cleanup_soft_deleted(
    conn: asyncpg.Connection,
    table: str,
    days: int = 30
) -> int:
    """清理超过指定天数的软删除记录

    Args:
        conn: 数据库连接
        table: 表名
        days: 保留天数，默认30天

    Returns:
        int: 清理的记录数
    """
    if table not in SOFT_DELETE_TABLES:
        raise ValueError(f"Table {table} does not support soft delete")

    result = await conn.execute(
        f"""
        DELETE FROM {table}
        WHERE deleted_at IS NOT NULL
        AND deleted_at < NOW() - INTERVAL '{days} days'
        """
    )

    try:
        count = int(result.split()[1]) if result.split() else 0
    except (IndexError, ValueError):
        count = 0

    if count > 0:
        logger.info(
            f"Cleaned up {count} soft-deleted records from {table}",
            extra={"action": "soft_delete_cleanup", "table": table, "count": count}
        )

    return count
