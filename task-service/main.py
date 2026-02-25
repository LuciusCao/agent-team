"""
Task Management Service - Main Application
"""

import os
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import get_db
from security import rate_limit
from routers import projects, tasks, agents, dashboard, channels

# Import utilities
from utils import setup_logging

# ============ Structured Logging ============

setup_logging()
logger = logging.getLogger("task_service")

# ============ Constants ============

SENSITIVE_FIELDS = {'api_key', 'token', 'password', 'secret', 'authorization', 'x-api-key'}


def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """清理日志数据中的敏感信息
    
    Args:
        data: 原始日志数据
        
    Returns:
        清理后的数据，敏感字段替换为 ***
    """
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELDS:
            sanitized[key] = '***'
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        elif isinstance(value, str) and any(sf in key.lower() for sf in SENSITIVE_FIELDS):
            # 如果 key 包含敏感字段名，也进行脱敏
            sanitized[key] = value[:3] + '***' if len(value) > 3 else '***'
        else:
            sanitized[key] = value
    return sanitized


# ============ FastAPI App ============

app = FastAPI(
    title="Task Management Service",
    version="1.2.0",
    redirect_slashes=False  # 禁用自动重定向，允许不带斜杠的 URL
)

# CORS 配置
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    logger.warning("CORS is configured to allow all origins. This is insecure for production.")
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=CORS_ORIGINS != "*",
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

_start_time = datetime.utcnow()

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
    
    uptime = (datetime.utcnow() - _start_time).total_seconds()
    
    return {
        "status": "healthy",
        "version": "1.2.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": db_status,
        "uptime_seconds": uptime
    }


# ============ Include Routers ============

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(channels.router, prefix="/agent-channels", tags=["channels"])
app.include_router(channels.channels_router, prefix="/channels", tags=["channels"])


# ============ Background Tasks ============

@app.on_event("startup")
async def startup_event():
    from background import heartbeat_monitor, stuck_task_monitor
    asyncio.create_task(heartbeat_monitor())
    asyncio.create_task(stuck_task_monitor())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
