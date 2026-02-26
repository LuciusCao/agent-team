"""
Task Management Service - Main Application
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from database import get_db
from routers import agents, channels, dashboard, projects, tasks
from security import rate_limit

# Import utilities
from utils import setup_logging

# ============ Structured Logging ============

setup_logging()
logger = logging.getLogger("task_service")

# ============ Constants ============

SENSITIVE_FIELDS = {'api_key', 'token', 'password', 'secret', 'authorization', 'x-api-key'}


def sanitize_log_data(data: dict[str, Any]) -> dict[str, Any]:
    """清理日志数据中的敏感信息

    递归检查所有字符串值，检测并脱敏敏感信息。

    Args:
        data: 原始日志数据

    Returns:
        清理后的数据，敏感字段和敏感值替换为 ***
    """
    if not isinstance(data, dict):
        return data

    def is_sensitive_key(key: str) -> bool:
        """检查 key 是否包含敏感字段名"""
        return any(sf in key.lower() for sf in SENSITIVE_FIELDS)

    def mask_sensitive_value(value: str) -> str:
        """脱敏敏感值"""
        if len(value) <= 3:
            return "***"
        return value[:3] + "***"

    def contains_sensitive_pattern(value: str) -> tuple[bool, list[str]]:
        """检查字符串值是否包含敏感模式（如密码、token 等）

        Returns:
            tuple: (是否包含敏感模式, 匹配到的模式列表)
        """
        patterns = [
            r"password\s*[=:]\s*\S+",
            r"token\s*[=:]\s*\S+",
            r"api[_-]?key\s*[=:]\s*\S+",
            r"secret\s*[=:]\s*\S+",
            r"authorization\s*[=:]\s*\S+",
        ]
        import re
        matched = [p for p in patterns if re.search(p, value, re.IGNORECASE)]
        return bool(matched), matched

    def sanitize_value(key: str, value: Any) -> Any:
        """递归脱敏值"""
        if isinstance(value, dict):
            return {k: sanitize_value(k, v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(key, item) for item in value]
        elif isinstance(value, str):
            # 如果 key 是敏感字段，脱敏整个值
            if is_sensitive_key(key):
                return mask_sensitive_value(value)
            # 如果值包含敏感模式，尝试脱敏
            has_sensitive, patterns = contains_sensitive_pattern(value)
            if has_sensitive:
                import re
                result = value
                for pattern in patterns:
                    result = re.sub(
                        pattern,
                        lambda m: m.group(0).split("=")[0] + "=***" if "=" in m.group(0) else m.group(0).split(":")[0] + ":***",
                        result,
                        flags=re.IGNORECASE
                    )
                return result
            return value
        return value

    sanitized = {}
    for key, value in data.items():
        sanitized[key] = sanitize_value(key, value)

    return sanitized


# ============ FastAPI App ============

app = FastAPI(
    title="Task Management Service",
    version="1.2.0",
    redirect_slashes=False  # 禁用自动重定向，允许不带斜杠的 URL
)

# CORS 配置
if Config.CORS_ORIGINS == "*":
    logger.warning("CORS is configured to allow all origins. This is insecure for production.")
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in Config.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=Config.CORS_ORIGINS != "*",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ============ Request Logging Middleware ============

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件（带敏感信息过滤）"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip,
            "action": "http_request"
        }

        # 清理敏感信息
        safe_log_data = sanitize_log_data(log_data)

        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration_ms:.2f}ms",
            extra=safe_log_data
        )
        return response
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip,
            "error": str(e),
            "action": "http_request_error"
        }

        # 清理敏感信息
        safe_log_data = sanitize_log_data(log_data)

        logger.error(
            f"{request.method} {request.url.path} - ERROR - {duration_ms:.2f}ms",
            extra=safe_log_data,
            exc_info=True
        )
        raise


# ============ Root Endpoint ============

@app.get("/")
async def root():
    return {"status": "ok", "service": "task-management", "version": "1.2.0"}


# ============ Health Check ============

_start_time = datetime.now(UTC)

@app.get("/health", dependencies=[Depends(rate_limit)])
async def health_check(db=Depends(get_db)):
    """详细健康检查端点"""
    try:
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}", extra={"action": "health_check_failed"})
        raise HTTPException(status_code=503, detail=f"Database connection failed: {e}")

    uptime = (datetime.now(UTC) - _start_time).total_seconds()

    return {
        "status": "healthy",
        "version": "1.2.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_status,
        "uptime_seconds": uptime
    }


# ============ Include Routers ============

# API v1 路由
app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/v1/tasks", tags=["tasks"])
app.include_router(agents.router, prefix="/v1/agents", tags=["agents"])
app.include_router(dashboard.router, prefix="/v1/dashboard", tags=["dashboard"])
app.include_router(channels.router, prefix="/v1/agent-channels", tags=["channels"])
app.include_router(channels.channels_router, prefix="/v1/channels", tags=["channels"])

# 向后兼容：保留无版本前缀的路由（deprecated）
app.include_router(projects.router, prefix="/projects", tags=["projects (deprecated)"], deprecated=True)
app.include_router(tasks.router, prefix="/tasks", tags=["tasks (deprecated)"], deprecated=True)
app.include_router(agents.router, prefix="/agents", tags=["agents (deprecated)"], deprecated=True)
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard (deprecated)"], deprecated=True)
app.include_router(channels.router, prefix="/agent-channels", tags=["channels (deprecated)"], deprecated=True)
app.include_router(channels.channels_router, prefix="/channels", tags=["channels (deprecated)"], deprecated=True)


# ============ Background Tasks ============

@app.on_event("startup")
async def startup_event():
    from background import heartbeat_monitor, soft_delete_cleanup_monitor, stuck_task_monitor
    asyncio.create_task(heartbeat_monitor())
    asyncio.create_task(stuck_task_monitor())
    asyncio.create_task(soft_delete_cleanup_monitor())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
