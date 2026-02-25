"""
Pydantic models for request/response validation
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class AgentRegister(BaseModel):
    name: str
    discord_user_id: Optional[str] = None
    role: str
    capabilities: Optional[dict] = None
    skills: Optional[List[str]] = None


class AgentHeartbeat(BaseModel):
    name: str
    current_task_id: Optional[int] = None


class AgentChannel(BaseModel):
    agent_name: str
    channel_id: str


class ProjectCreate(BaseModel):
    name: str
    discord_channel_id: Optional[str] = None
    description: Optional[str] = None


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    task_type: str
    priority: Optional[int] = 5
    assignee_agent: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_mention: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    parent_task_id: Optional[int] = None
    dependencies: Optional[List[int]] = None
    task_tags: Optional[List[str]] = None
    estimated_hours: Optional[float] = None
    timeout_minutes: Optional[int] = None
    created_by: Optional[str] = None
    due_at: Optional[datetime] = None  # Pydantic 自动验证 ISO 格式


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict] = None
    assignee_agent: Optional[str] = None
    priority: Optional[int] = None
    feedback: Optional[str] = None


class TaskReview(BaseModel):
    approved: bool
    feedback: Optional[str] = None


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: str
    database: str
    uptime_seconds: Optional[float] = None
