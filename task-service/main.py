"""
Task Management Service - Main Application
"""

import os
import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import get_db
from security import rate_limit
from routers import projects, tasks, agents, dashboard, channels, channels_router

# Import utilities
from utils import JSONFormatter

# ============ Structured Logging ============

logger = logging.getLogger("task_service")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logger.handlers = [handler]

logging.getLogger("uvicorn").handlers = [handler]
logging.getLogger("uvicorn.access").handlers = [handler]

# ============ FastAPI App ============

app = FastAPI(title="Task Management Service", version="1.2.0")

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
    """请求日志中间件"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        
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

app.include_router(projects, prefix="/projects", tags=["projects"])
app.include_router(tasks, prefix="/tasks", tags=["tasks"])
app.include_router(agents, prefix="/agents", tags=["agents"])
app.include_router(dashboard, prefix="/dashboard", tags=["dashboard"])
app.include_router(channels, prefix="/agent-channels", tags=["channels"])
app.include_router(channels_router, prefix="/channels", tags=["channels"])


# ============ Background Tasks ============

@app.on_event("startup")
async def startup_event():
    from background import heartbeat_monitor, stuck_task_monitor
    asyncio.create_task(heartbeat_monitor())
    asyncio.create_task(stuck_task_monitor())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
