"""
Routers package
"""

from .projects import router as projects
from .tasks import router as tasks
from .agents import router as agents
from .dashboard import router as dashboard
from .channels import router as channels, channels_router

__all__ = ["projects", "tasks", "agents", "dashboard", "channels", "channels_router"]
