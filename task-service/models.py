"""
Pydantic models for request/response validation
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentRegister(BaseModel):
    name: str = Field(..., max_length=100)
    discord_user_id: str | None = Field(None, max_length=100)
    role: str = Field(..., max_length=50)
    capabilities: dict | None = None
    skills: list[str] | None = None


class AgentHeartbeat(BaseModel):
    name: str = Field(..., max_length=100)
    current_task_id: int | None = None


class AgentChannel(BaseModel):
    agent_name: str = Field(..., max_length=100)
    channel_id: str = Field(..., max_length=50)


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    discord_channel_id: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=5000)


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(..., max_length=500)
    description: str | None = Field(None, max_length=10000)
    task_type: str = Field(..., max_length=50)
    priority: int | None = Field(5, ge=1, le=10)
    assignee_agent: str | None = Field(None, max_length=100)
    reviewer_id: str | None = Field(None, max_length=100)
    reviewer_mention: str | None = Field(None, max_length=100)
    acceptance_criteria: str | None = Field(None, max_length=5000)
    parent_task_id: int | None = None
    dependencies: list[int] | None = None
    task_tags: list[str] | None = None
    estimated_hours: float | None = Field(None, ge=0)
    timeout_minutes: int | None = Field(None, ge=1)
    created_by: str | None = Field(None, max_length=100)
    due_at: datetime | None = None  # Pydantic 自动验证 ISO 格式


class TaskUpdate(BaseModel):
    status: str | None = Field(None, max_length=50)
    result: dict | None = None
    assignee_agent: str | None = Field(None, max_length=100)
    priority: int | None = Field(None, ge=1, le=10)
    feedback: str | None = Field(None, max_length=10000)


class TaskReview(BaseModel):
    approved: bool
    feedback: str | None = Field(None, max_length=5000)


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: str
    database: str
    uptime_seconds: float | None = None
