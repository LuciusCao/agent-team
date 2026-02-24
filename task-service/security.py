"""
Security utilities - API Key and Rate Limiting
"""

import os
from datetime import datetime
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Rate limiting
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
rate_limit_store = {}


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
