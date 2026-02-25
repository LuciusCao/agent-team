"""
Security utilities - API Key and Rate Limiting
"""

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from config import Config
from utils import RateLimiter

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# 使用统一的 RateLimiter 类
_rate_limiter = RateLimiter(
    window=Config.RATE_LIMIT_WINDOW,
    max_requests=Config.RATE_LIMIT_MAX_REQUESTS,
    max_store_size=Config.RATE_LIMIT_MAX_STORE_SIZE
)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """验证 API Key

    如果环境变量 API_KEY 未设置，则跳过验证（开发环境）。
    生产环境必须设置 API_KEY。
    """
    if Config.API_KEY is None or Config.API_KEY == "":
        return None

    if api_key is None:
        raise HTTPException(status_code=403, detail="API Key required")

    if api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    return api_key


async def rate_limit(request: Request):
    """简单的速率限制

    基于客户端 IP 的滑动窗口限流。
    生产环境建议使用 Redis。
    """
    client_ip = request.client.host if request.client else "unknown"

    if not _rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {Config.RATE_LIMIT_MAX_REQUESTS} requests per {Config.RATE_LIMIT_WINDOW} seconds"
        )

    return True
