"""
Pydantic models for request/response validation
"""

from datetime import datetime

from pydantic import BaseModel


class AgentRegister(BaseModel):
    name: str
    discord_user_id: str | None = None
    role: str
    capabilities: dict | None = None
    skills: list[str] | None = None


class AgentHeartbeat(BaseModel):
    name: str
    current_task_id: int | None = None


class AgentChannel(BaseModel):
    agent_name: str
    channel_id: str


class ProjectCreate(BaseModel):
    name: str
    discord_channel_id: str | None = None
    description: str | None = None


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: str | None = None
    task_type: str
    priority: int | None = 5
    assignee_agent: str | None = None
    reviewer_id: str | None = None
    reviewer_mention: str | None = None
    acceptance_criteria: str | None = None
    parent_task_id: int | None = None
    dependencies: list[int] | None = None
    task_tags: list[str] | None = None
    estimated_hours: float | None = None
    timeout_minutes: int | None = None
    created_by: str | None = None
    due_at: datetime | None = None  # Pydantic 自动验证 ISO 格式


class TaskUpdate(BaseModel):
    status: str | None = None
    result: dict | None = None
    assignee_agent: str | None = None
    priority: int | None = None
    feedback: str | None = None


class TaskReview(BaseModel):
    approved: bool
    feedback: str | None = None


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: str
    database: str
    uptime_seconds: float | None = None
