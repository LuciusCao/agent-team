#!/usr/bin/env python3
"""
Task Management Service v1.2
FastAPI + PostgreSQL
Agent Workforce Extensions + Configurable Timeouts + Structured Logging
"""

import os
import json
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, List
from functools import wraps
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import asyncpg

# ============ Structured Logging ============

class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
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

# 配置日志
logger = logging.getLogger("task_service")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# 控制台处理器
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.handlers = [handler]

# 禁用默认的 uvicorn 日志传播（保持 JSON 格式纯净）
logging.getLogger("uvicorn").handlers = [handler]
logging.getLogger("uvicorn.access").handlers = [handler]

app = FastAPI(title="Task Management Service", version="1.2.0")

# CORS 配置 - 生产环境应该限制具体域名
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    logger.warning("CORS is configured to allow all origins. This is insecure for production.")
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=CORS_ORIGINS != "*",  # 允许所有来源时不能同时允许 credentials
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ============ Request Logging Middleware ============

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件
    
    记录每个请求的方法、路径、状态码和处理时间。
    """
    start_time = time.time()
    
    # 获取客户端 IP
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        
        # 记录成功请求
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration_ms:.2f}ms",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": client_ip,
                "action": "http_request"
            }
        )
        
        return response
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        
        # 记录异常请求
        logger.error(
            f"{request.method} {request.url.path} - ERROR - {duration_ms:.2f}ms - {e}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
                "client_ip": client_ip,
                "error": str(e),
                "action": "http_request_error"
            },
            exc_info=True
        )
        raise

# Database
DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/taskmanager")
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()

# Security
API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Rate limiting
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
rate_limit_store = {}  # Simple in-memory store

# Idempotency
IDEMPOTENCY_KEY_TTL = 86400  # 24 hours


# ============ Connection Retry Decorator ============

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


async def check_idempotency(conn: asyncpg.Connection, idempotency_key: Optional[str] = None):
    """检查幂等性（数据库持久化版本）
    
    如果提供了幂等键且已存在，返回缓存的响应。
    否则返回 None，表示需要执行操作。
    
    Args:
        conn: 数据库连接
        idempotency_key: 幂等键（通常由客户端生成 UUID）
    
    Returns:
        tuple: (cached_response, should_skip)
    """
    if not idempotency_key:
        return None, False
    
    # 清理过期的幂等键（使用数据库）
    await conn.execute(
        "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours'"
    )
    
    # 检查幂等键是否存在
    row = await conn.fetchrow(
        "SELECT response FROM idempotency_keys WHERE key = $1",
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


async def store_idempotency_response(conn: asyncpg.Connection, idempotency_key: Optional[str], response: dict):
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
    """存储幂等响应
    
    Args:
        idempotency_key: 幂等键
        response: 响应数据
    """
    if idempotency_key:
        idempotency_store[idempotency_key] = (response, datetime.now().timestamp())
        logger.debug(
            f"Stored idempotency response for key: {idempotency_key}",
            extra={"idempotency_key": idempotency_key, "action": "idempotency_store"}
        )


async def get_db():
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:  # 双重检查
                _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return _pool


# ============ Health Check ============

class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: str
    database: str
    uptime_seconds: Optional[float] = None


_start_time = datetime.utcnow()


@app.get("/health", response_model=HealthStatus)
async def health_check(db=Depends(get_db)):
    """详细健康检查端点
    
    检查服务状态和数据库连接。
    """
    try:
        # 检查数据库连接
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}", extra={"action": "health_check_failed"})
        db_status = "disconnected"
        raise HTTPException(status_code=503, detail=f"Database connection failed: {e}")
    
    uptime = (datetime.utcnow() - _start_time).total_seconds()
    
    return HealthStatus(
        status="healthy",
        version="1.2.0",
        timestamp=datetime.utcnow().isoformat() + "Z",
        database=db_status,
        uptime_seconds=uptime
    )


async def verify_api_key(api_key: str = Security(api_key_header)):
    """验证 API Key
    
    如果环境变量 API_KEY 未设置，则跳过验证（开发环境）。
    生产环境必须设置 API_KEY。
    """
    if API_KEY is None:
        # 开发环境：未设置 API_KEY 时不验证
        return None
    
    if api_key is None:
        raise HTTPException(status_code=403, detail="API Key required")
    
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    return api_key


async def rate_limit(request: Request):
    """简单的速率限制
    
    基于客户端 IP 的滑动窗口限流。
    生产环境建议使用 Redis。
    """
    client_ip = request.client.host
    current_time = datetime.now().timestamp()
    
    # 清理过期的记录
    if client_ip in rate_limit_store:
        rate_limit_store[client_ip] = [
            ts for ts in rate_limit_store[client_ip]
            if current_time - ts < RATE_LIMIT_WINDOW
        ]
    else:
        rate_limit_store[client_ip] = []
    
    # 检查是否超过限制
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds"
        )
    
    # 记录本次请求
    rate_limit_store[client_ip].append(current_time)
    
    return True


# ============ Pydantic Models ============

class AgentRegister(BaseModel):
    name: str
    discord_user_id: Optional[str] = None
    role: str
    capabilities: Optional[dict] = None
    skills: Optional[List[str]] = None


class AgentHeartbeat(BaseModel):
    name: str
    current_task_id: Optional[int] = None


class AgentChannel(BaseModel):
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
    priority: Optional[int] = 5
    assignee_agent: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_mention: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    parent_task_id: Optional[int] = None
    dependencies: Optional[List[int]] = None
    task_tags: Optional[List[str]] = None
    estimated_hours: Optional[float] = None
    timeout_minutes: Optional[int] = None  # 任务超时（分钟），NULL 使用默认值
    created_by: Optional[str] = None
    due_at: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict] = None
    assignee_agent: Optional[str] = None
    priority: Optional[int] = None
    feedback: Optional[str] = None


class TaskReview(BaseModel):
    approved: bool
    feedback: Optional[str] = None


# ============ Dependency Check ============

async def check_dependencies(conn: asyncpg.Connection, task_id: int) -> tuple[bool, List[int]]:
    """检查任务依赖是否完成"""
    task = await conn.fetchrow("SELECT dependencies FROM tasks WHERE id = $1", task_id)
    if not task or not task["dependencies"]:
        return True, []
    
    deps = task["dependencies"]
    
    # 检查所有依赖任务是否完成
    for dep_id in deps:
        dep = await conn.fetchrow(
            "SELECT status FROM tasks WHERE id = $1",
            dep_id
        )
        if not dep or dep["status"] != "completed":
            return False, deps
    
    return True, []



def validate_task_dependencies(tasks: List[TaskCreate]) -> None:
    """验证任务依赖关系，检测循环依赖"""
    from collections import defaultdict, deque
    
    n = len(tasks)
    graph = defaultdict(list)
    in_degree = [0] * n
    
    for i, task in enumerate(tasks):
        if task.dependencies:
            for dep_idx in task.dependencies:
                if dep_idx < 0 or dep_idx >= n:
                    raise HTTPException(status_code=400, detail=f"Invalid dependency index: {dep_idx}")
                if dep_idx == i:
                    raise HTTPException(status_code=400, detail=f"Task cannot depend on itself")
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

# ============ Agent Status Helper ============

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


# ============ API Routes ============

@app.get("/")
async def root():
    return {"status": "ok", "service": "task-management", "version": "1.2.0"}


# ============ Project Endpoints ============

@app.post("/projects", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def create_project(project: ProjectCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO projects (name, discord_channel_id, description)
            VALUES ($1, $2, $3)
            RETURNING id, name, discord_channel_id, description, status, created_at
            """,
            project.name, project.discord_channel_id, project.description
        )
    return result


@app.get("/projects", dependencies=[Depends(rate_limit)])
async def list_projects(status: Optional[str] = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if status:
            results = await conn.fetch(
                "SELECT * FROM projects WHERE status = $1 ORDER BY created_at DESC",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM projects ORDER BY created_at DESC")
    return results


@app.get("/projects/{project_id}", dependencies=[Depends(rate_limit)])
async def get_project(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/projects/{project_id}/progress", dependencies=[Depends(rate_limit)])
async def get_project_progress(project_id: int, db=Depends(get_db)):
    """获取项目进度统计"""
    async with db.acquire() as conn:
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 统计任务状态
        stats = await conn.fetchrow(
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
            FROM tasks WHERE project_id = $1
            """,
            project_id
        )
        
        total = stats["total"] or 0
        completed = stats["completed"] or 0
        progress = (completed / total * 100) if total > 0 else 0
    
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "total_tasks": total,
        "stats": dict(stats),
        "progress_percent": round(progress, 1)
    }


@app.post("/projects/{project_id}/breakdown", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def breakdown_project(project_id: int, tasks: List[TaskCreate], db=Depends(get_db)):
    """项目拆分：批量创建任务
    
    会自动验证依赖关系，检测循环依赖。
    """
    # 验证依赖关系（在数据库操作前）
    validate_task_dependencies(tasks)
    
    async with db.acquire() as conn:
        # 检查项目存在
        project = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        created_tasks = []
        for task in tasks:
            result = await conn.fetchrow(
                """
                INSERT INTO tasks (
                    project_id, title, description, task_type, priority,
                    assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                    parent_task_id, dependencies, task_tags, estimated_hours, created_by, due_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING *
                """,
                project_id, task.title, task.description, task.task_type, task.priority,
                task.assignee_agent, task.reviewer_id, task.reviewer_mention, task.acceptance_criteria,
                task.parent_task_id, task.dependencies, task.task_tags, task.estimated_hours,
                task.created_by, task.due_at
            )
            
            # 记录日志
            await conn.execute(
                "INSERT INTO task_logs (task_id, action, message, actor) VALUES ($1, $2, $3, $4)",
                result["id"], "created", f"Task created via breakdown: {task.title}", task.created_by or "system"
            )
            
            created_tasks.append(dict(result))
    
    return {"project_id": project_id, "tasks_created": len(created_tasks), "tasks": created_tasks}


# ============ Task Endpoints ============

@app.post("/tasks", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def create_task(task: TaskCreate, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO tasks (
                project_id, title, description, task_type, priority,
                assignee_agent, reviewer_id, reviewer_mention, acceptance_criteria,
                parent_task_id, dependencies, task_tags, estimated_hours, timeout_minutes, created_by, due_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING *
            """,
            task.project_id, task.title, task.description, task.task_type, task.priority,
            task.assignee_agent, task.reviewer_id, task.reviewer_mention, task.acceptance_criteria,
            task.parent_task_id, task.dependencies, task.task_tags, task.estimated_hours,
            task.timeout_minutes, task.created_by, task.due_at
        )
        
        logger.info(
            f"Task created: {task.title} (ID: {result['id']})",
            extra={
                "task_id": result["id"],
                "project_id": task.project_id,
                "task_type": task.task_type,
                "action": "task_created",
                "created_by": task.created_by or "system"
            }
        )
    return result


@app.get("/tasks", dependencies=[Depends(rate_limit)])
async def list_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    task_type: Optional[str] = None,
    tags: Optional[List[str]] = Query(None),
    db=Depends(get_db)
):
    """列出任务，支持多种过滤条件"""
    conditions = ["1=1"]
    params = []
    
    if project_id:
        params.append(project_id)
        conditions.append(f"project_id = ${len(params)}")
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if assignee:
        params.append(assignee)
        conditions.append(f"assignee_agent = ${len(params)}")
    if task_type:
        params.append(task_type)
        conditions.append(f"task_type = ${len(params)}")
    if tags:
        # 检查是否包含任一标签
        params.append(tags)
        conditions.append(f"task_tags && ${len(params)}")
    
    query = f"SELECT * FROM tasks WHERE {' AND '.join(conditions)} ORDER BY priority DESC, created_at DESC"
    
    async with db.acquire() as conn:
        results = await conn.fetch(query, *params)
    return results



@app.get("/tasks/available", dependencies=[Depends(rate_limit)])
async def get_available_tasks(db=Depends(get_db)):
    """获取可认领的任务（pending 状态，没有 assignee，依赖已完成）
    
    使用 SQL 子查询一次性过滤掉依赖未完成的任务，避免 N+1 查询。
    """
    async with db.acquire() as conn:
        # 使用 NOT EXISTS 一次性查询依赖已完成的任务
        # 避免 Python 循环中的 N+1 查询
        results = await conn.fetch(
            """
            SELECT t.* 
            FROM tasks t
            WHERE t.status = 'pending' 
            AND t.assignee_agent IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM tasks dep 
                WHERE dep.id = ANY(t.dependencies) 
                AND dep.status != 'completed'
            )
            ORDER BY t.priority DESC, t.created_at ASC
            """
        )
    
    return [dict(row) for row in results]


@app.get("/tasks/available-for/{agent_name}", dependencies=[Depends(rate_limit)])
async def get_available_tasks_for_agent(
    agent_name: str,
    skill_match: bool = True,
    db=Depends(get_db)
):
    """获取适合某 Agent 的任务（带技能匹配）
    
    使用 SQL JOIN 和子查询一次性完成依赖检查和技能匹配，避免 N+1 查询。
    """
    async with db.acquire() as conn:
        # 获取 Agent 信息
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent_skills = agent["skills"] or []
        
        if skill_match and agent_skills:
            # 技能匹配模式：使用数组交集操作符 &&
            # 一次性完成：依赖检查 + 技能匹配
            results = await conn.fetch(
                """
                SELECT t.* 
                FROM tasks t
                WHERE t.status = 'pending' 
                AND t.assignee_agent IS NULL
                AND t.task_tags && $1  -- 技能标签匹配
                AND NOT EXISTS (
                    SELECT 1 FROM tasks dep 
                    WHERE dep.id = ANY(t.dependencies) 
                    AND dep.status != 'completed'
                )
                ORDER BY t.priority DESC, t.created_at ASC
                """,
                agent_skills
            )
        else:
            # 无技能匹配：只检查依赖
            results = await conn.fetch(
                """
                SELECT t.* 
                FROM tasks t
                WHERE t.status = 'pending' 
                AND t.assignee_agent IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM tasks dep 
                    WHERE dep.id = ANY(t.dependencies) 
                    AND dep.status != 'completed'
                )
                ORDER BY t.priority DESC, t.created_at ASC
                """
            )
    
    return [dict(row) for row in results]


@app.post("/tasks/{task_id}/claim", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def claim_task(
    task_id: int, 
    agent_name: str, 
    idempotency_key: Optional[str] = None,
    db=Depends(get_db)
):
    """Agent 认领任务（带依赖检查、原子性乐观锁和幂等性）
    
    支持多任务模式，但限制最大并发任务数（默认 3 个）。
    
    幂等性：提供相同的 idempotency_key 会返回相同的结果，不会重复认领。
    """
    # 最大并发任务数配置
    MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS_PER_AGENT", "3"))
    
    async with db.acquire() as conn:
        # 检查幂等性（在事务内检查）
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached
        
        # 检查依赖
        deps_ok, deps = await check_dependencies(conn, task_id)
        if not deps_ok:
            raise HTTPException(status_code=400, detail=f"Dependencies not completed: {deps}")
        
        # 检查 Agent 当前并发任务数
        current_tasks = await conn.fetchrow(
            """
            SELECT COUNT(*) as count 
            FROM tasks 
            WHERE assignee_agent = $1 AND status IN ('assigned', 'running', 'reviewing')
            """,
            agent_name
        )
        
        if current_tasks['count'] >= MAX_CONCURRENT_TASKS:
            raise HTTPException(
                status_code=429, 
                detail=f"Agent {agent_name} has reached maximum concurrent tasks limit ({MAX_CONCURRENT_TASKS})"
            )
        
        # 原子性认领：使用 UPDATE ... RETURNING 确保只有一个 Agent 能成功
        # 这避免了 SELECT + UPDATE 之间的竞态条件
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET assignee_agent = $1, status = 'assigned', assigned_at = NOW(), updated_at = NOW()
            WHERE id = $2 AND status = 'pending' AND assignee_agent IS NULL
            RETURNING *
            """,
            agent_name, task_id
        )
        
        if not result:
            # 任务已被其他 Agent 认领或状态已变更
            raise HTTPException(status_code=409, detail="Task already claimed by another agent or not available")
        
        # 更新 Agent 状态
        await conn.execute(
            """
            UPDATE agents 
            SET status = 'busy', current_task_id = $1, updated_at = NOW()
            WHERE name = $2
            """,
            task_id, agent_name
        )
        
        # 记录日志
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "claimed", "pending", "assigned", f"Task claimed by {agent_name}", agent_name
        )
        
        logger.info(
            f"Task {task_id} claimed by {agent_name}",
            extra={
                "task_id": task_id,
                "agent_name": agent_name,
                "action": "task_claimed",
                "idempotency_key": idempotency_key
            }
        )
        
        # 存储幂等响应（在事务内）
        response = dict(result)
        await store_idempotency_response(conn, idempotency_key, response)
    
    return result


@app.post("/tasks/{task_id}/start", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def start_task(task_id: int, agent_name: str, db=Depends(get_db)):
    """Agent 开始执行任务
    
    限制：一个 Agent 同一时间只能执行一个任务（running 状态）。
    可以认领多个任务（assigned），但只能依次执行。
    """
    async with db.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
        
        if task["status"] != "assigned":
            raise HTTPException(status_code=400, detail=f"Cannot start task with status: {task['status']}")
        
        # 检查是否已经有执行中的任务
        running_task = await conn.fetchrow(
            "SELECT id, title FROM tasks WHERE assignee_agent = $1 AND status = 'running'",
            agent_name
        )
        if running_task:
            raise HTTPException(
                status_code=409, 
                detail=f"Already has a running task (#{running_task['id']} - {running_task['title']}). "
                       f"Please complete or release it before starting a new one."
            )
        
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'running', started_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "started", "assigned", "running", f"Task started by {agent_name}", agent_name
        )
    
    return result


@app.post("/tasks/{task_id}/submit", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def submit_task(
    task_id: int, 
    agent_name: str, 
    result: dict, 
    idempotency_key: Optional[str] = None,
    db=Depends(get_db)
):
    """Agent 提交任务完成，进入验收阶段
    
    幂等性：提供相同的 idempotency_key 会返回相同的结果，不会重复提交。
    """
    async with db.acquire() as conn:
        # 检查幂等性（在事务内）
        cached, should_skip = await check_idempotency(conn, idempotency_key)
        if should_skip:
            return cached
        
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
        
        if task["status"] != "running":
            raise HTTPException(status_code=400, detail=f"Cannot submit task with status: {task['status']}")
        
        updated = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'reviewing', result = $1, updated_at = NOW()
            WHERE id = $2
            RETURNING *
            """,
            json.dumps(result), task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "submitted", "running", "reviewing", f"Task submitted for review by {agent_name}", agent_name
        )
        
        logger.info(
            f"Task {task_id} submitted by {agent_name}",
            extra={
                "task_id": task_id,
                "agent_name": agent_name,
                "action": "task_submitted",
                "idempotency_key": idempotency_key
            }
        )
        
        # 存储幂等响应（在事务内）
        response = dict(updated)
        await store_idempotency_response(conn, idempotency_key, response)
    
    return updated


@app.post("/tasks/{task_id}/release", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def release_task(task_id: int, agent_name: str, db=Depends(get_db)):
    """Agent 释放任务（重新变成 pending）
    
    注意：如果 Agent 有多个任务，释放一个后状态应该保持 busy，
    直到所有任务都完成或释放。
    """
    async with db.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT * FROM tasks WHERE id = $1 AND assignee_agent = $2",
            task_id, agent_name
        )
        if not task:
            raise HTTPException(status_code=404, detail="Task not found or not assigned to you")
        
        # 只能释放 assigned 或 running 状态的任务
        if task["status"] not in ["assigned", "running"]:
            raise HTTPException(status_code=400, detail=f"Cannot release task with status: {task['status']}")
        
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET assignee_agent = NULL, status = 'pending', assigned_at = NULL, started_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )
        
        # 更新 Agent 状态（考虑多任务场景）
        await update_agent_status_after_task_change(conn, agent_name)
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "released", task["status"], "pending", f"Task released by {agent_name}", agent_name
        )
    
    return result


@app.post("/tasks/{task_id}/retry", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def retry_task(task_id: int, db=Depends(get_db)):
    """重试失败或被拒绝的任务"""
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task["status"] not in ["failed", "rejected"]:
            raise HTTPException(status_code=400, detail=f"Cannot retry task with status: {task['status']}")
        
        if task["retry_count"] >= task["max_retries"]:
            raise HTTPException(status_code=400, detail=f"Max retries ({task['max_retries']}) exceeded")
        
        result = await conn.fetchrow(
            """
            UPDATE tasks 
            SET status = 'pending', assignee_agent = NULL, retry_count = retry_count + 1,
                assigned_at = NULL, started_at = NULL, updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "retry", task["status"], "pending", f"Task retry (attempt {result['retry_count']})", "system"
        )
    
    return result


@app.get("/tasks/{task_id}", dependencies=[Depends(rate_limit)])
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


@app.patch("/tasks/{task_id}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def update_task(task_id: int, update: TaskUpdate, db=Depends(get_db)):
    async with db.acquire() as conn:
        current = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not current:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 构建更新
        updates = []
        params = []
        param_num = 1
        
        if update.status is not None:
            updates.append(f"status = ${param_num}")
            params.append(update.status)
            param_num += 1
            
            if update.status == "completed":
                updates.append("completed_at = NOW()")
                
                # 更新 Agent 统计
                if current["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents 
                        SET completed_tasks = completed_tasks + 1, 
                            total_tasks = total_tasks + 1,
                            success_rate = (completed_tasks::FLOAT + 1) / NULLIF(total_tasks + 1, 0),
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        current["assignee_agent"]
                    )
                    # 更新 Agent 状态（考虑多任务场景）
                    await update_agent_status_after_task_change(conn, current["assignee_agent"])
            elif update.status == "failed":
                if current["assignee_agent"]:
                    await conn.execute(
                        """
                        UPDATE agents 
                        SET failed_tasks = failed_tasks + 1,
                            total_tasks = total_tasks + 1,
                            success_rate = (completed_tasks::FLOAT) / NULLIF(total_tasks + 1, 0),
                            updated_at = NOW()
                        WHERE name = $1
                        """,
                        current["assignee_agent"]
                    )
                    # 更新 Agent 状态（考虑多任务场景）
                    await update_agent_status_after_task_change(conn, current["assignee_agent"])
        
        if update.result is not None:
            updates.append(f"result = ${param_num}")
            params.append(json.dumps(update.result))
            param_num += 1
        
        if update.assignee_agent is not None:
            updates.append(f"assignee_agent = ${param_num}")
            params.append(update.assignee_agent)
            param_num += 1
        
        if update.priority is not None:
            updates.append(f"priority = ${param_num}")
            params.append(update.priority)
            param_num += 1
        
        if update.feedback is not None:
            updates.append(f"feedback = ${param_num}")
            params.append(update.feedback)
            param_num += 1
        
        if not updates:
            return current
        
        updates.append("updated_at = NOW()")
        params.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ${param_num} RETURNING *"
        
        result = await conn.fetchrow(query, *params)
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message)
            VALUES ($1, $2, $3, $4, $5)
            """,
            task_id, "status_changed", current["status"], update.status or current["status"],
            f"Task updated: {update.dict(exclude_none=True)}"
        )
    
    return result


@app.post("/tasks/{task_id}/review", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def review_task(task_id: int, review: TaskReview, reviewer: str, db=Depends(get_db)):
    """验收任务 - 支持通过、拒绝"""
    async with db.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task["status"] != "reviewing":
            raise HTTPException(status_code=400, detail=f"Cannot review task with status: {task['status']}")
        
        if review.approved:
            new_status = "completed"
            # 更新 Agent 统计
            if task["assignee_agent"]:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET completed_tasks = completed_tasks + 1,
                        updated_at = NOW()
                    WHERE name = $1
                    """,
                    task["assignee_agent"]
                )
                # 更新 Agent 状态（考虑多任务场景）
                await update_agent_status_after_task_change(conn, task["assignee_agent"])
        else:
            new_status = "rejected"
            # 更新 Agent 统计
            if task["assignee_agent"]:
                await conn.execute(
                    """
                    UPDATE agents 
                    SET failed_tasks = failed_tasks + 1,
                        updated_at = NOW()
                    WHERE name = $1
                    """,
                    task["assignee_agent"]
                )
                # 更新 Agent 状态（考虑多任务场景）
                await update_agent_status_after_task_change(conn, task["assignee_agent"])
        
        await conn.execute(
            """
            UPDATE tasks SET status = $1, feedback = $2, updated_at = NOW(), completed_at = CASE WHEN $1 = 'completed' THEN NOW() ELSE NULL END
            WHERE id = $3
            """,
            new_status, review.feedback, task_id
        )
        
        await conn.execute(
            """
            INSERT INTO task_logs (task_id, action, old_status, new_status, message, actor)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            task_id, "reviewed", task["status"], new_status,
            f"Reviewed by {reviewer}: {'approved' if review.approved else 'rejected'}. Feedback: {review.feedback}",
            reviewer
        )
        
        updated = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    
    return updated


@app.get("/projects/{project_id}/tasks", dependencies=[Depends(rate_limit)])
async def get_project_tasks(project_id: int, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM tasks WHERE project_id = $1 ORDER BY priority DESC, created_at DESC",
            project_id
        )
    return results


# ============ Agent Endpoints ============

@app.post("/agents/register", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
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
                last_heartbeat = NOW()
            RETURNING *
            """,
            agent.name, agent.discord_user_id, agent.role,
            json.dumps(agent.capabilities) if agent.capabilities else None,
            agent.skills
        )
    return result


@app.post("/agents/{name}/heartbeat", dependencies=[Depends(rate_limit)])
async def agent_heartbeat(name: str, data: AgentHeartbeat, db=Depends(get_db)):
    async with db.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE agents SET status = 'online', last_heartbeat = NOW(), current_task_id = $2, updated_at = NOW()
            WHERE name = $1 RETURNING *
            """,
            name, data.current_task_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Agent not found")
    return result


@app.get("/agents", dependencies=[Depends(rate_limit)])
async def list_agents(status: Optional[str] = None, skill: Optional[str] = None, db=Depends(get_db)):
    async with db.acquire() as conn:
        if skill:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE skills @> ARRAY[$1] ORDER BY name",
                skill
            )
        elif status:
            results = await conn.fetch(
                "SELECT * FROM agents WHERE status = $1 ORDER BY name",
                status
            )
        else:
            results = await conn.fetch("SELECT * FROM agents ORDER BY name")
    return results


@app.get("/agents/{name}", dependencies=[Depends(rate_limit)])
async def get_agent(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        agent = await conn.fetchrow("SELECT * FROM agents WHERE name = $1", name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.delete("/agents/{name}", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def unregister_agent(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM agents WHERE name = $1", name)
    return {"message": f"Agent {name} unregistered"}


# ============ Dashboard Endpoints ============

@app.get("/dashboard/stats", dependencies=[Depends(rate_limit)])
async def get_dashboard_stats(db=Depends(get_db)):
    """获取仪表盘统计数据"""
    async with db.acquire() as conn:
        # 项目统计
        project_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active
            FROM projects
            """
        )
        
        # 任务统计
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
        
        # Agent 统计
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
        
        # 最近活动
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


# ============ Agent Channel Endpoints ============

@app.post("/agent-channels", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
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


@app.get("/agents/{name}/channels", dependencies=[Depends(rate_limit)])
async def get_agent_channels(name: str, db=Depends(get_db)):
    async with db.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM agent_channels WHERE agent_name = $1 ORDER BY last_seen DESC",
            name
        )
    return results


@app.get("/channels/{channel_id}/agents", dependencies=[Depends(rate_limit)])
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


@app.delete("/agent-channels", dependencies=[Depends(verify_api_key), Depends(rate_limit)])
async def unregister_agent_channel(ac: AgentChannel, db=Depends(get_db)):
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM agent_channels WHERE agent_name = $1 AND channel_id = $2",
            ac.agent_name, ac.channel_id
        )
    return {"message": f"Agent {ac.agent_name} removed from channel {ac.channel_id}"}


# ============ Background Tasks ============

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(heartbeat_monitor())
    asyncio.create_task(stuck_task_monitor())


async def heartbeat_monitor():
    """监控 Agent 心跳，超时设为 offline
    
    使用全局连接池，避免每次循环创建新连接池的开销和潜在的连接泄露。
    """
    global _pool
    while True:
        await asyncio.sleep(60)
        try:
            # 确保连接池已初始化
            if _pool is None:
                async with _pool_lock:
                    if _pool is None:
                        _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
            
            async with _pool.acquire() as conn:
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
            # 出错时重置连接池，下次循环会重新创建
            async with _pool_lock:
                _pool = None


async def stuck_task_monitor():
    """监控卡住的任务，自动释放
    
    支持配置化超时时间：
    - 任务级别的 timeout_minutes
    - 任务类型默认配置（task_type_defaults 表）
    - 全局默认 120 分钟
    
    使用全局连接池，避免每次循环创建新连接池的开销和潜在的连接泄露。
    """
    global _pool
    DEFAULT_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_TASK_TIMEOUT_MINUTES", "120"))
    
    while True:
        await asyncio.sleep(600)  # 每10分钟检查一次
        try:
            # 确保连接池已初始化
            if _pool is None:
                async with _pool_lock:
                    if _pool is None:
                        _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
            
            async with _pool.acquire() as conn:
                # 找出卡住的任务（使用配置化超时）
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
                    
                    # 释放任务
                    await conn.execute(
                        """
                        UPDATE tasks 
                        SET status = 'pending', assignee_agent = NULL, 
                            assigned_at = NULL, started_at = NULL, updated_at = NOW()
                        WHERE id = $1
                        """,
                        task["id"]
                    )
                    
                    # 更新 Agent 状态
                    if task["assignee_agent"]:
                        await update_agent_status_after_task_change(conn, task["assignee_agent"])
                    
                    # 记录日志
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
            # 出错时重置连接池，下次循环会重新创建
            async with _pool_lock:
                _pool = None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
