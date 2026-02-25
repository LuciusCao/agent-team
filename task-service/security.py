"""
Security utilities - API Key and Rate Limiting
"""

import os
from datetime import datetime

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Rate limiting
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
RATE_LIMIT_MAX_STORE_SIZE = int(os.getenv("RATE_LIMIT_MAX_STORE_SIZE", "10000"))
rate_limit_store = {}
_last_cleanup_time = 0


def _cleanup_rate_limit_store(current_time: float) -> None:
    """清理速率限制存储中的过期记录

    当存储大小超过阈值或距离上次清理超过窗口时间时执行清理。
    """
    global _last_cleanup_time

    # 检查是否需要清理
    if len(rate_limit_store) < RATE_LIMIT_MAX_STORE_SIZE and current_time - _last_cleanup_time < RATE_LIMIT_WINDOW:
        return

    # 清理过期记录
    expired_threshold = current_time - RATE_LIMIT_WINDOW
    expired_ips = [
        ip for ip, timestamps in rate_limit_store.items()
        if not timestamps or all(ts < expired_threshold for ts in timestamps)
    ]

    for ip in expired_ips:
        del rate_limit_store[ip]

    _last_cleanup_time = current_time


async def verify_api_key(api_key: str = Security(api_key_header)):
    """验证 API Key

    如果环境变量 API_KEY 未设置，则跳过验证（开发环境）。
    生产环境必须设置 API_KEY。
    """
    if API_KEY is None:
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

    # 定期清理过期记录，防止内存泄漏
    _cleanup_rate_limit_store(current_time)

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
