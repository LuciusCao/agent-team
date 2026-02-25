"""
集中配置管理

所有配置项集中在此文件，避免分散在代码各处。
"""

import os


class Config:
    """应用配置类"""

    # 数据库配置
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/taskmanager")
    DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
    DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
    DB_COMMAND_TIMEOUT = int(os.getenv("DB_COMMAND_TIMEOUT", "60"))
    DB_MAX_QUERIES = int(os.getenv("DB_MAX_QUERIES", "100000"))

    # API 配置
    API_KEY = os.getenv("API_KEY")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # 速率限制配置
    RATE_LIMIT_WINDOW = 60  # 秒
    RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
    RATE_LIMIT_MAX_STORE_SIZE = int(os.getenv("RATE_LIMIT_MAX_STORE_SIZE", "10000"))

    # 任务配置
    MAX_CONCURRENT_TASKS_PER_AGENT = int(os.getenv("MAX_CONCURRENT_TASKS_PER_AGENT", "3"))
    DEFAULT_TASK_TIMEOUT_MINUTES = int(os.getenv("DEFAULT_TASK_TIMEOUT_MINUTES", "120"))

    # Agent 心跳配置
    AGENT_OFFLINE_THRESHOLD_MINUTES = 5
    HEARTBEAT_INTERVAL_SECONDS = 60

    # 卡住任务检测配置
    STUCK_TASK_CHECK_INTERVAL_SECONDS = 600

    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def is_production(cls) -> bool:
        """检查是否为生产环境"""
        return cls.API_KEY is not None and cls.API_KEY != ""

    @classmethod
    def validate(cls) -> list[str]:
        """验证配置有效性

        Returns:
            list[str]: 错误信息列表，空列表表示配置有效
        """
        errors = []

        if cls.DB_POOL_MIN_SIZE > cls.DB_POOL_MAX_SIZE:
            errors.append("DB_POOL_MIN_SIZE cannot be greater than DB_POOL_MAX_SIZE")

        if cls.MAX_CONCURRENT_TASKS_PER_AGENT < 1:
            errors.append("MAX_CONCURRENT_TASKS_PER_AGENT must be at least 1")

        if cls.DEFAULT_TASK_TIMEOUT_MINUTES < 1:
            errors.append("DEFAULT_TASK_TIMEOUT_MINUTES must be at least 1")

        return errors
