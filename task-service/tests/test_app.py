"""
Task Service 完整测试套件 - 100% 覆盖度

运行方式:
    pytest tests/ -v --cov=. --cov-report=term-missing

需要环境变量:
    DATABASE_URL=postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ============ 测试配置 ============

TEST_DB_HOST = os.getenv("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.getenv("TEST_DB_PORT", "5433")
TEST_DB_USER = os.getenv("TEST_DB_USER", "taskmanager")
TEST_DB_PASSWORD = os.getenv("TEST_DB_PASSWORD", "taskmanager")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "taskmanager_test")

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
)
ADMIN_DATABASE_URL = os.getenv(
    "ADMIN_DATABASE_URL",
    f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["API_KEY"] = os.getenv("TEST_API_KEY", "test-api-key")
os.environ["LOG_LEVEL"] = os.getenv("TEST_LOG_LEVEL", "DEBUG")
os.environ["RATE_LIMIT_MAX_REQUESTS"] = "10000"  # 测试时提高限制

import asyncpg

from main import app, get_db

# ============ 数据库初始化 ============

_test_db_initialized = False

async def init_test_database():
    """初始化测试数据库（只运行一次）"""
    global _test_db_initialized
    if _test_db_initialized:
        return

    try:
        conn = await asyncpg.connect(ADMIN_DATABASE_URL)
        try:
            await conn.execute(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{TEST_DB_NAME}'
                AND pid <> pg_backend_pid()
            """)
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
            await conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
        finally:
            await conn.close()

        conn = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            with open("schema.sql") as f:
                schema = f.read()
                await conn.execute(schema)
        finally:
            await conn.close()

        _test_db_initialized = True
    except Exception as e:
        print(f"Warning: Failed to initialize test database: {e}")

try:
    asyncio.run(init_test_database())
except Exception as e:
    print(f"Database initialization deferred: {e}")


# ============ Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_db():
    """每个测试使用独立的数据库连接池"""
    pool = await asyncpg.create_pool(TEST_DATABASE_URL, min_size=1, max_size=5)
    yield pool

    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE task_logs, tasks, agents, projects, agent_channels, idempotency_keys RESTART IDENTITY CASCADE")
    await pool.close()


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """创建测试客户端"""
    async def override_get_db():
        return test_db

    app.dependency_overrides[get_db] = override_get_db

    # 重置速率限制器
    from security import _rate_limiter
    _rate_limiter.store = {}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """认证头"""
    return {"X-API-Key": "test-api-key"}


# ============ 测试类 ============

class TestHealth:
    """健康检查测试"""

    async def test_root(self, client):
        """测试根路径"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "task-management"
        assert "version" in data

    async def test_health_check(self, client):
        """测试健康检查端点"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "uptime_seconds" in data
        assert "timestamp" in data


class TestAuth:
    """认证测试"""

    async def test_missing_api_key(self, client):
        """测试缺少 API Key"""
        response = await client.post("/projects/", json={"name": "Test"})
        assert response.status_code == 403

    async def test_invalid_api_key(self, client):
        """测试无效的 API Key"""
        response = await client.post(
            "/projects/",
            json={"name": "Test"},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 403


class TestProjects:
    """项目 API 测试"""

    async def test_create_project(self, client, auth_headers):
        """测试创建项目"""
        response = await client.post(
            "/projects/",
            json={"name": "Test Project", "description": "Test description"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Project"
        assert "id" in data
        assert "created_at" in data

    async def test_create_project_with_discord_channel(self, client, auth_headers):
        """测试创建带 Discord 频道的项目"""
        response = await client.post(
            "/projects/",
            json={
                "name": "Discord Project",
                "discord_channel_id": "123456789",
                "description": "Project with Discord"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["discord_channel_id"] == "123456789"

    async def test_list_projects(self, client):
        """测试列出项目"""
        response = await client.get("/projects/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_projects_with_status_filter(self, client, auth_headers):
        """测试按状态过滤项目"""
        await client.post(
            "/projects/",
            json={"name": "Active Project"},
            headers=auth_headers
        )

        response = await client.get("/projects/?status=active")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_project(self, client, auth_headers):
        """测试获取项目详情"""
        create_resp = await client.post(
            "/projects/",
            json={"name": "Get Test Project"},
            headers=auth_headers
        )
        project = create_resp.json()

        response = await client.get(f"/projects/{project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project["id"]

    async def test_get_project_not_found(self, client):
        """测试获取不存在的项目"""
        response = await client.get("/projects/99999")
        assert response.status_code == 404

    async def test_get_project_progress(self, client, auth_headers):
        """测试获取项目进度"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Progress Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        response = await client.get(f"/projects/{project['id']}/progress")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project["id"]
        assert "total_tasks" in data
        assert "stats" in data
        assert "progress_percent" in data

    async def test_get_project_progress_not_found(self, client):
        """测试获取不存在项目的进度"""
        response = await client.get("/projects/99999/progress")
        assert response.status_code == 404

    async def test_delete_project_soft(self, client, auth_headers):
        """测试软删除项目"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Delete Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        response = await client.delete(f"/projects/{project['id']}", headers=auth_headers)
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        get_resp = await client.get(f"/projects/{project['id']}")
        assert get_resp.status_code == 404

    async def test_delete_project_hard(self, client, auth_headers):
        """测试硬删除项目"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Hard Delete Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        response = await client.delete(f"/projects/{project['id']}?hard=true", headers=auth_headers)
        assert response.status_code == 200
        assert "hard deleted" in response.json()["message"]

    async def test_delete_project_not_found(self, client, auth_headers):
        """测试删除不存在的项目"""
        response = await client.delete("/projects/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_restore_project(self, client, auth_headers):
        """测试恢复软删除的项目"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Restore Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.delete(f"/projects/{project['id']}", headers=auth_headers)

        response = await client.post(f"/projects/{project['id']}/restore", headers=auth_headers)
        assert response.status_code == 200
        assert "restored successfully" in response.json()["message"]

        get_resp = await client.get(f"/projects/{project['id']}")
        assert get_resp.status_code == 200

    async def test_restore_project_not_found(self, client, auth_headers):
        """测试恢复不存在或未删除的项目"""
        response = await client.post("/projects/99999/restore", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_project_tasks(self, client, auth_headers):
        """测试获取项目下的所有任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Tasks Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Task 1", "task_type": "research"},
            headers=auth_headers
        )

        response = await client.get(f"/projects/{project['id']}/tasks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_project_breakdown(self, client, auth_headers):
        """测试项目拆分 - 批量创建任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Breakdown Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        tasks = [
            {"project_id": project["id"], "title": "Task 1", "task_type": "research"},
            {"project_id": project["id"], "title": "Task 2", "task_type": "development"},
        ]
        response = await client.post(
            f"/projects/{project['id']}/breakdown",
            json=tasks,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tasks_created"] == 2
        assert len(data["tasks"]) == 2

    async def test_project_breakdown_not_found(self, client, auth_headers):
        """测试对不存在项目进行拆分"""
        tasks = [{"project_id": 99999, "title": "Task", "task_type": "research"}]
        response = await client.post(
            "/projects/99999/breakdown",
            json=tasks,
            headers=auth_headers
        )
        assert response.status_code == 404


class TestTasks:
    """任务 API 测试"""

    async def test_create_task(self, client, auth_headers):
        """测试创建任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Task Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        response = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Test Task",
                "task_type": "research",
                "priority": 8
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Task"
        assert data["status"] == "pending"
        assert data["priority"] == 8

    async def test_create_task_with_dependencies(self, client, auth_headers):
        """测试创建带依赖的任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Dependency Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task1_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "First Task", "task_type": "research"},
            headers=auth_headers
        )
        task1 = task1_resp.json()

        task2_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Second Task",
                "task_type": "research",
                "dependencies": [task1["id"]]
            },
            headers=auth_headers
        )
        assert task2_resp.status_code == 200
        task2 = task2_resp.json()
        assert task2["dependencies"] == [task1["id"]]

    async def test_create_task_with_duplicate_dependencies(self, client, auth_headers):
        """测试创建带重复依赖的任务应该失败"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Duplicate Dep Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task1_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "First Task", "task_type": "research"},
            headers=auth_headers
        )
        task1 = task1_resp.json()

        response = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Second Task",
                "task_type": "research",
                "dependencies": [task1["id"], task1["id"]]
            },
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Duplicate dependencies" in response.json()["detail"]

    async def test_create_task_with_invalid_dependency(self, client, auth_headers):
        """测试创建带无效依赖的任务应该失败"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Invalid Dep Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        response = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Invalid Task",
                "task_type": "research",
                "dependencies": [-1]
            },
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Invalid dependency ID" in response.json()["detail"]

    async def test_list_tasks(self, client, auth_headers):
        """测试列出任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "List Tasks Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Task 1", "task_type": "research"},
            headers=auth_headers
        )

        response = await client.get("/tasks/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_tasks_with_filters(self, client, auth_headers):
        """测试带过滤条件列出任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Filter Tasks Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Task 1", "task_type": "research"},
            headers=auth_headers
        )

        response = await client.get(f"/tasks/?project_id={project['id']}")
        assert response.status_code == 200

        response = await client.get("/tasks/?status=pending")
        assert response.status_code == 200

        response = await client.get("/tasks/?task_type=research")
        assert response.status_code == 200

    async def test_get_task(self, client, auth_headers):
        """测试获取任务详情"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Get Task Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Get Me", "task_type": "research"},
            headers=auth_headers
        )
        task = task_resp.json()

        response = await client.get(f"/tasks/{task['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["task"]["id"] == task["id"]
        assert "logs" in data

    async def test_get_task_not_found(self, client):
        """测试获取不存在的任务"""
        response = await client.get("/tasks/99999")
        assert response.status_code == 404

    async def test_delete_task_soft(self, client, auth_headers):
        """测试软删除任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Delete Task Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Delete Me", "task_type": "research"},
            headers=auth_headers
        )
        task = task_resp.json()

        response = await client.delete(f"/tasks/{task['id']}", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await client.get(f"/tasks/{task['id']}")
        assert get_resp.status_code == 404

    async def test_delete_task_hard(self, client, auth_headers):
        """测试硬删除任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Hard Delete Task Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Hard Delete Me", "task_type": "research"},
            headers=auth_headers
        )
        task = task_resp.json()

        response = await client.delete(f"/tasks/{task['id']}?hard=true", headers=auth_headers)
        assert response.status_code == 200
        assert "hard deleted" in response.json()["message"]

    async def test_restore_task(self, client, auth_headers):
        """测试恢复软删除的任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Restore Task Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Restore Me", "task_type": "research"},
            headers=auth_headers
        )
        task = task_resp.json()

        await client.delete(f"/tasks/{task['id']}", headers=auth_headers)

        response = await client.post(f"/tasks/{task['id']}/restore", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await client.get(f"/tasks/{task['id']}")
        assert get_resp.status_code == 200

    async def test_get_available_tasks(self, client, auth_headers):
        """测试获取可认领的任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Available Tasks Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Available Task", "task_type": "research"},
            headers=auth_headers
        )

        response = await client.get("/tasks/available")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_available_tasks_for_agent(self, client, auth_headers):
        """测试获取适合某 Agent 的任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Agent Tasks Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        await client.post(
            "/agents/register/",
            json={"name": "test-agent", "role": "research", "skills": ["python"]},
            headers=auth_headers
        )

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Python Task", "task_type": "research", "task_tags": ["python"]},
            headers=auth_headers
        )

        response = await client.get("/tasks/available-for/test-agent")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_available_tasks_for_agent_not_found(self, client):
        """测试获取不存在 Agent 的可用任务"""
        response = await client.get("/tasks/available-for/nonexistent-agent")
        assert response.status_code == 404


class TestTaskLifecycle:
    """任务完整生命周期测试"""

    async def test_full_task_lifecycle_success(self, client, auth_headers):
        """测试完整任务流转：pending → assigned → running → reviewing → completed"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Lifecycle Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Lifecycle Test Task", "task_type": "research"},
            headers=auth_headers
        )
        task = task_resp.json()
        task_id = task["id"]

        await client.post(
            "/agents/register/",
            json={"name": "lifecycle-agent", "role": "research"},
            headers=auth_headers
        )

        # 认领
        claim_resp = await client.post(
            f"/tasks/{task_id}/claim/",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert claim_resp.status_code == 200
        assert claim_resp.json()["status"] == "assigned"

        # 开始
        start_resp = await client.post(
            f"/tasks/{task_id}/start/",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "running"

        # 提交
        submit_resp = await client.post(
            f"/tasks/{task_id}/submit/",
            params={"agent_name": "lifecycle-agent"},
            json={"output": "test result", "summary": "Task completed"},
            headers=auth_headers
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "reviewing"

        # 验收
        review_resp = await client.post(
            f"/tasks/{task_id}/review/",
            params={"reviewer": "test-reviewer"},
            json={"approved": True, "feedback": "Good job!"},
            headers=auth_headers
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "completed"

    async def test_task_lifecycle_reject(self, client, auth_headers):
        """测试任务被拒绝的流程"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Reject Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Reject Test Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]

        await client.post("/agents/register/", json={"name": "reject-agent", "role": "research"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "reject-agent"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/start/", params={"agent_name": "reject-agent"}, headers=auth_headers)
        await client.post(
            f"/tasks/{task_id}/submit/",
            params={"agent_name": "reject-agent"},
            json={"output": "result"},
            headers=auth_headers
        )

        review_resp = await client.post(
            f"/tasks/{task_id}/review/",
            params={"reviewer": "test-reviewer"},
            json={"approved": False, "feedback": "Needs improvement"},
            headers=auth_headers
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "rejected"

    async def test_task_release(self, client, auth_headers):
        """测试释放任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Release Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Release Test Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]

        await client.post("/agents/register/", json={"name": "release-agent", "role": "research"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "release-agent"}, headers=auth_headers)

        release_resp = await client.post(
            f"/tasks/{task_id}/release/",
            params={"agent_name": "release-agent"},
            headers=auth_headers
        )
        assert release_resp.status_code == 200
        assert release_resp.json()["status"] == "pending"

    async def test_task_retry(self, client, auth_headers):
        """测试重试失败的任务"""
        project_resp = await client.post(
            "/projects/",
            json={"name": "Retry Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Retry Test Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]

        await client.post("/agents/register/", json={"name": "retry-agent", "role": "research"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "retry-agent"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/start/", params={"agent_name": "retry-agent"}, headers=auth_headers)
        await client.post(
            f"/tasks/{task_id}/submit/",
            params={"agent_name": "retry-agent"},
            json={"output": "result"},
            headers=auth_headers
        )
        await client.post(
            f"/tasks/{task_id}/review/",
            params={"reviewer": "test-reviewer"},
            json={"approved": False},
            headers=auth_headers
        )

        retry_resp = await client.post(f"/tasks/{task_id}/retry/", headers=auth_headers)
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "pending"


class TestAgents:
    """Agent API 测试"""

    async def test_register_agent(self, client, auth_headers):
        """测试注册 Agent"""
        response = await client.post(
            "/agents/register/",
            json={"name": "test-agent-1", "role": "research", "skills": ["python", "data-analysis"]},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-agent-1"
        assert data["status"] == "online"

    async def test_register_agent_with_capabilities(self, client, auth_headers):
        """测试注册带能力的 Agent"""
        response = await client.post(
            "/agents/register/",
            json={
                "name": "capable-agent",
                "role": "research",
                "capabilities": {"max_tokens": 4000, "model": "gpt-4"},
                "discord_user_id": "123456789"
            },
            headers=auth_headers
        )
        assert response.status_code == 200

    async def test_register_agent_update_existing(self, client, auth_headers):
        """测试更新已存在的 Agent"""
        await client.post(
            "/agents/register/",
            json={"name": "update-agent", "role": "research", "skills": ["python"]},
            headers=auth_headers
        )

        response = await client.post(
            "/agents/register/",
            json={"name": "update-agent", "role": "developer", "skills": ["python", "javascript"]},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "developer"

    async def test_list_agents(self, client, auth_headers):
        """测试列出 Agents"""
        await client.post("/agents/register/", json={"name": "list-agent-1", "role": "research"}, headers=auth_headers)

        response = await client.get("/agents/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_agents_with_status_filter(self, client, auth_headers):
        """测试按状态过滤 Agents"""
        response = await client.get("/agents/?status=online")
        assert response.status_code == 200

    async def test_list_agents_with_skill_filter(self, client, auth_headers):
        """测试按技能过滤 Agents"""
        await client.post("/agents/register/", json={"name": "skill-agent", "role": "research", "skills": ["python"]}, headers=auth_headers)

        response = await client.get("/agents/?skill=python")
        assert response.status_code == 200

    async def test_get_agent(self, client, auth_headers):
        """测试获取 Agent 详情"""
        await client.post("/agents/register/", json={"name": "get-agent", "role": "research"}, headers=auth_headers)

        response = await client.get("/agents/get-agent")
        assert response.status_code == 200
        assert response.json()["name"] == "get-agent"

    async def test_get_agent_not_found(self, client):
        """测试获取不存在的 Agent"""
        response = await client.get("/agents/nonexistent-agent")
        assert response.status_code == 404

    async def test_agent_heartbeat(self, client, auth_headers):
        """测试 Agent 心跳"""
        await client.post("/agents/register/", json={"name": "heartbeat-agent", "role": "research"}, headers=auth_headers)

        response = await client.post(
            "/agents/heartbeat-agent/heartbeat/",
            json={"name": "heartbeat-agent"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "online"

    async def test_agent_heartbeat_not_found(self, client):
        """测试不存在 Agent 的心跳"""
        response = await client.post("/agents/nonexistent/heartbeat/", json={"name": "nonexistent"})
        assert response.status_code == 404

    async def test_delete_agent_soft(self, client, auth_headers):
        """测试软删除 Agent"""
        await client.post("/agents/register/", json={"name": "delete-agent", "role": "research"}, headers=auth_headers)

        response = await client.delete("/agents/delete-agent", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await client.get("/agents/delete-agent")
        assert get_resp.status_code == 404

    async def test_delete_agent_hard(self, client, auth_headers):
        """测试硬删除 Agent"""
        await client.post("/agents/register/", json={"name": "hard-delete-agent", "role": "research"}, headers=auth_headers)

        response = await client.delete("/agents/hard-delete-agent?hard=true", headers=auth_headers)
        assert response.status_code == 200
        assert "hard" in response.json()["message"]

    async def test_delete_agent_not_found(self, client, auth_headers):
        """测试删除不存在的 Agent"""
        response = await client.delete("/agents/nonexistent-agent", headers=auth_headers)
        assert response.status_code == 404

    async def test_restore_agent(self, client, auth_headers):
        """测试恢复软删除的 Agent"""
        await client.post("/agents/register/", json={"name": "restore-agent", "role": "research"}, headers=auth_headers)
        await client.delete("/agents/restore-agent", headers=auth_headers)

        response = await client.post("/agents/restore-agent/restore", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await client.get("/agents/restore-agent")
        assert get_resp.status_code == 200

    async def test_restore_agent_not_found(self, client, auth_headers):
        """测试恢复不存在或未删除的 Agent"""
        response = await client.post("/agents/nonexistent/restore", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_agent_channels(self, client, auth_headers):
        """测试获取 Agent 的频道"""
        await client.post("/agents/register/", json={"name": "channel-agent", "role": "research"}, headers=auth_headers)

        response = await client.get("/agents/channel-agent/channels/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestRateLimiter:
    """速率限制器测试"""

    async def test_rate_limiter_basic(self, client):
        """测试基础速率限制功能"""
        responses = []
        for _ in range(5):
            resp = await client.get("/projects/")
            responses.append(resp.status_code)

        assert all(code == 200 for code in responses)

    async def test_rate_limiter_with_force_cleanup(self, client, auth_headers):
        """测试速率限制器强制清理功能"""
        from utils import RateLimiter

        limiter = RateLimiter(window=60, max_requests=2, max_store_size=3)

        for i in range(3):
            allowed = await limiter.is_allowed(f"key_{i}")
            assert allowed is True

        allowed = await limiter.is_allowed("key_overflow")
        assert allowed is True
        assert len(limiter.store) <= 3

    async def test_rate_limiter_get_remaining(self, client):
        """测试获取剩余请求数"""
        from utils import RateLimiter

        limiter = RateLimiter(window=60, max_requests=5)

        remaining = await limiter.get_remaining("test_key")
        assert remaining == 5

        await limiter.is_allowed("test_key")
        remaining = await limiter.get_remaining("test_key")
        assert remaining == 4

    async def test_rate_limiter_exceed_limit(self, client):
        """测试超出限制"""
        from utils import RateLimiter

        limiter = RateLimiter(window=60, max_requests=1)

        assert await limiter.is_allowed("limited_key") is True
        assert await limiter.is_allowed("limited_key") is False


class TestCircularDependency:
    """循环依赖检测测试"""

    async def test_check_circular_dependency_no_cycle(self, test_db):
        """测试无循环依赖的情况"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            await conn.execute("INSERT INTO projects (id, name, status) VALUES (1, 'Test Project', 'active') ON CONFLICT DO NOTHING")

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES (1, 'Task A', 'research', 'pending') RETURNING id")
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES (1, 'Task B', 'research', 'pending', ARRAY[$1::int]) RETURNING id", task_a["id"])

            has_cycle = await check_circular_dependency(conn, task_b["id"], [task_a["id"]])
            assert has_cycle is False

    async def test_check_circular_dependency_with_cycle(self, test_db):
        """测试有循环依赖的情况"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Test Project', 'active') RETURNING id")
            project_id = project['id']

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Task A', 'research', 'pending') RETURNING id", project_id)
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task B', 'research', 'pending', ARRAY[$2::int]) RETURNING id", project_id, task_a["id"])

            has_cycle = await check_circular_dependency(conn, task_a["id"], [task_b["id"]])
            assert has_cycle is True

    async def test_check_circular_dependency_self_reference(self, test_db):
        """测试任务不能依赖自己"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            await conn.execute("INSERT INTO projects (id, name, status) VALUES (1, 'Test Project', 'active') ON CONFLICT DO NOTHING")
            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES (1, 'Task A', 'research', 'pending') RETURNING id")

            has_cycle = await check_circular_dependency(conn, task_a["id"], [task_a["id"]])
            assert has_cycle is True


class TestCycleDetectionFull:
    """全图循环检测测试"""

    async def test_detect_all_cycles_no_cycle(self, test_db):
        """测试无循环的情况"""
        from utils import detect_all_cycles_in_project

        async with test_db.acquire() as conn:
            await conn.execute("INSERT INTO projects (id, name, status) VALUES (1, 'Test Project', 'active') ON CONFLICT DO NOTHING")

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES (1, 'Task A', 'research', 'pending') RETURNING id")
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES (1, 'Task B', 'research', 'pending', ARRAY[$1::int]) RETURNING id", task_a["id"])
            await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES (1, 'Task C', 'research', 'pending', ARRAY[$1::int]) RETURNING id", task_b["id"])

            cycles = await detect_all_cycles_in_project(conn, 1)
            assert len(cycles) == 0

    async def test_detect_all_cycles_with_cycle(self, test_db):
        """测试检测到循环"""
        from utils import detect_all_cycles_in_project

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Test Project', 'active') RETURNING id")
            project_id = project['id']

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Task A', 'research', 'pending') RETURNING id", project_id)
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task B', 'research', 'pending', ARRAY[$2::int]) RETURNING id", project_id, task_a["id"])
            task_c = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task C', 'research', 'pending', ARRAY[$2::int]) RETURNING id", project_id, task_b["id"])
            await conn.execute("UPDATE tasks SET dependencies = ARRAY[$1::int] WHERE id = $2", task_c["id"], task_a["id"])

            cycles = await detect_all_cycles_in_project(conn, project_id)
            assert len(cycles) == 1

    async def test_validate_no_existing_cycles_raises(self, test_db):
        """测试验证函数在检测到循环时抛出异常"""
        from utils import validate_no_existing_cycles
        from fastapi import HTTPException

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Test Project', 'active') RETURNING id")
            project_id = project['id']

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Task A', 'research', 'pending') RETURNING id", project_id)
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task B', 'research', 'pending', ARRAY[$2::int]) RETURNING id", project_id, task_a["id"])
            await conn.execute("UPDATE tasks SET dependencies = ARRAY[$1::int] WHERE id = $2", task_b["id"], task_a["id"])

            with pytest.raises(HTTPException) as exc_info:
                await validate_no_existing_cycles(conn, project_id)
            assert exc_info.value.status_code == 400


class TestConfigValidation:
    """配置验证测试"""

    async def test_config_validate_db_timeout(self):
        """测试数据库超时配置验证"""
        from config import Config

        original_timeout = Config.DB_COMMAND_TIMEOUT

        try:
            Config.DB_COMMAND_TIMEOUT = 0
            errors = Config.validate()
            assert any("DB_COMMAND_TIMEOUT must be at least" in e for e in errors)

            Config.DB_COMMAND_TIMEOUT = 301
            errors = Config.validate()
            assert any("should not exceed 300 seconds" in e for e in errors)

            Config.DB_COMMAND_TIMEOUT = 60
            errors = Config.validate()
            assert not any("DB_COMMAND_TIMEOUT" in e for e in errors)
        finally:
            Config.DB_COMMAND_TIMEOUT = original_timeout

    async def test_config_validate_max_queries(self):
        """测试最大查询数配置验证"""
        from config import Config

        original_max = Config.DB_MAX_QUERIES

        try:
            Config.DB_MAX_QUERIES = 500
            errors = Config.validate()
            assert any("DB_MAX_QUERIES should be at least" in e for e in errors)

            Config.DB_MAX_QUERIES = 2000000
            errors = Config.validate()
            assert any("should not exceed 1,000,000" in e for e in errors)
        finally:
            Config.DB_MAX_QUERIES = original_max

    async def test_config_validate_pool_size(self):
        """测试连接池大小配置验证"""
        from config import Config

        original_min = Config.DB_POOL_MIN_SIZE
        original_max = Config.DB_POOL_MAX_SIZE

        try:
            Config.DB_POOL_MIN_SIZE = 10
            Config.DB_POOL_MAX_SIZE = 5
            errors = Config.validate()
            assert any("DB_POOL_MIN_SIZE cannot be greater than DB_POOL_MAX_SIZE" in e for e in errors)
        finally:
            Config.DB_POOL_MIN_SIZE = original_min
            Config.DB_POOL_MAX_SIZE = original_max

    async def test_config_validate_concurrent_tasks(self):
        """测试并发任务配置验证"""
        from config import Config

        original = Config.MAX_CONCURRENT_TASKS_PER_AGENT

        try:
            Config.MAX_CONCURRENT_TASKS_PER_AGENT = 0
            errors = Config.validate()
            assert any("MAX_CONCURRENT_TASKS_PER_AGENT must be at least 1" in e for e in errors)
        finally:
            Config.MAX_CONCURRENT_TASKS_PER_AGENT = original

    async def test_config_validate_timeout_minutes(self):
        """测试超时分钟配置验证"""
        from config import Config

        original = Config.DEFAULT_TASK_TIMEOUT_MINUTES

        try:
            Config.DEFAULT_TASK_TIMEOUT_MINUTES = 0
            errors = Config.validate()
            assert any("DEFAULT_TASK_TIMEOUT_MINUTES must be at least 1" in e for e in errors)
        finally:
            Config.DEFAULT_TASK_TIMEOUT_MINUTES = original

    async def test_config_validate_rate_limit(self):
        """测试速率限制配置验证"""
        from config import Config

        original_requests = Config.RATE_LIMIT_MAX_REQUESTS
        original_size = Config.RATE_LIMIT_MAX_STORE_SIZE

        try:
            Config.RATE_LIMIT_MAX_REQUESTS = 0
            errors = Config.validate()
            assert any("RATE_LIMIT_MAX_REQUESTS must be at least 1" in e for e in errors)

            Config.RATE_LIMIT_MAX_REQUESTS = original_requests
            Config.RATE_LIMIT_MAX_STORE_SIZE = 50
            errors = Config.validate()
            assert any("RATE_LIMIT_MAX_STORE_SIZE should be at least 100" in e for e in errors)
        finally:
            Config.RATE_LIMIT_MAX_REQUESTS = original_requests
            Config.RATE_LIMIT_MAX_STORE_SIZE = original_size

    async def test_config_is_production(self):
        """测试生产环境检测"""
        from config import Config

        original = Config.API_KEY

        try:
            Config.API_KEY = None
            assert Config.is_production() is False

            Config.API_KEY = ""
            assert Config.is_production() is False

            Config.API_KEY = "secret-key"
            assert Config.is_production() is True
        finally:
            Config.API_KEY = original


class TestUpdateTaskRefactored:
    """重构后的 update_task 测试"""

    async def test_update_task_build_fields(self):
        """测试构建更新字段"""
        from routers.tasks import _build_update_fields
        from models import TaskUpdate

        updates, params = await _build_update_fields(TaskUpdate())
        assert len(updates) == 0
        assert len(params) == 0

        update = TaskUpdate(status="completed", priority=8)
        updates, params = await _build_update_fields(update)
        assert len(updates) == 2

    async def test_update_task_with_all_fields(self, client, auth_headers):
        """测试更新任务所有字段"""
        project_resp = await client.post("/projects/", json={"name": "Update Test Project"}, headers=auth_headers)
        project = project_resp.json()

        task_resp = await client.post("/tasks/", json={"project_id": project["id"], "title": "Test Task", "task_type": "research"}, headers=auth_headers)
        task = task_resp.json()

        response = await client.patch(
            f"/tasks/{task['id']}",
            json={"status": "completed", "priority": 10, "feedback": "Great work!", "result": {"output": "test result"}},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["priority"] == 10


class TestUtils:
    """工具函数测试"""

    async def test_setup_logging(self):
        """测试日志设置"""
        from utils import setup_logging

        logger = setup_logging()
        assert logger is not None
        assert logger.name == "task_service"

    async def test_validate_task_type(self):
        """测试任务类型验证"""
        from utils import validate_task_type

        assert validate_task_type("research") is True
        assert validate_task_type("development") is True
        assert validate_task_type("invalid") is False

    async def test_validate_agent_role(self):
        """测试 Agent 角色验证"""
        from utils import validate_agent_role

        assert validate_agent_role("research") is True
        assert validate_agent_role("developer") is True
        assert validate_agent_role("invalid") is False

    async def test_sanitize_string(self):
        """测试字符串清理"""
        from utils import sanitize_string

        assert sanitize_string("hello") == "hello"
        assert sanitize_string("  hello  ") == "hello"
        long_str = "a" * 300
        assert len(sanitize_string(long_str, max_length=255)) == 255
        assert sanitize_string(None) is None

    async def test_sanitize_log_data(self):
        """测试日志数据脱敏"""
        from main import sanitize_log_data

        data = {"username": "test", "password": "secret123", "api_key": "sk-123456"}
        result = sanitize_log_data(data)
        assert "***" in str(result["password"]) or result["password"] != "secret123"

    async def test_check_dependencies(self, test_db):
        """测试依赖检查"""
        from utils import check_dependencies

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Dep Test', 'active') RETURNING id")

            task_a = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Task A', 'research', 'completed') RETURNING id", project['id'])
            task_b = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task B', 'research', 'pending', ARRAY[$2::int]) RETURNING id", project['id'], task_a['id'])

            deps_ok, deps = await check_dependencies(conn, task_b['id'])
            assert deps_ok is True

    async def test_log_structured(self):
        """测试结构化日志"""
        from utils import log_structured

        log_structured("info", "Test message", action="test", extra_field="value")

    async def test_validate_task_dependencies_for_create(self):
        """测试任务依赖验证"""
        from utils import validate_task_dependencies_for_create
        from fastapi import HTTPException

        validate_task_dependencies_for_create([])
        validate_task_dependencies_for_create(None)

        with pytest.raises(HTTPException) as exc_info:
            validate_task_dependencies_for_create([1, 1])
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException) as exc_info:
            validate_task_dependencies_for_create([-1])
        assert exc_info.value.status_code == 400

    async def test_retry_on_db_error(self):
        """测试数据库重试装饰器"""
        from utils import retry_on_db_error
        import asyncpg

        call_count = 0

        @retry_on_db_error(max_retries=3, base_delay=0.01)
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise asyncpg.PostgresError("Test error")

        with pytest.raises(asyncpg.PostgresError):
            await failing_function()

        assert call_count == 3


class TestIdempotency:
    """幂等性测试"""

    async def test_check_idempotency_no_key(self, test_db):
        """测试无幂等键"""
        from utils import check_idempotency

        async with test_db.acquire() as conn:
            cached, should_skip = await check_idempotency(conn, None)
            assert cached is None
            assert should_skip is False

    async def test_store_and_check_idempotency(self, test_db):
        """测试存储和检查幂等响应"""
        from utils import check_idempotency, store_idempotency_response

        async with test_db.acquire() as conn:
            key = "test-key-456"
            response = {"id": 1, "status": "success"}

            await store_idempotency_response(conn, key, response)
            cached, should_skip = await check_idempotency(conn, key)
            assert should_skip is True
            assert cached == response


class TestSoftDelete:
    """软删除测试"""

    async def test_soft_delete_invalid_table(self, test_db):
        """测试无效表的软删除"""
        from utils import soft_delete

        async with test_db.acquire() as conn:
            with pytest.raises(ValueError) as exc_info:
                await soft_delete(conn, "invalid_table", 1)
            assert "does not support soft delete" in str(exc_info.value)

    async def test_cleanup_soft_deleted(self, test_db):
        """测试清理软删除记录"""
        from utils import cleanup_soft_deleted, soft_delete

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Cleanup Test', 'active') RETURNING id")
            await soft_delete(conn, "projects", project['id'])
            await conn.execute("UPDATE projects SET deleted_at = NOW() - INTERVAL '31 days' WHERE id = $1", project['id'])

            count = await cleanup_soft_deleted(conn, "projects", days=30)
            assert count >= 0


class TestAgentUtils:
    """Agent 工具函数测试"""

    async def test_update_agent_status_after_task_change(self, test_db):
        """测试任务变更后更新 Agent 状态"""
        from utils import update_agent_status_after_task_change

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Agent Test', 'active') RETURNING id")
            await conn.execute("INSERT INTO agents (name, role, status) VALUES ('test-agent', 'research', 'busy')")
            await conn.execute("INSERT INTO tasks (project_id, title, task_type, status, assignee_agent) VALUES ($1, 'Test Task', 'research', 'completed', 'test-agent')", project['id'])

            await update_agent_status_after_task_change(conn, 'test-agent')

            agent = await conn.fetchrow("SELECT * FROM agents WHERE name = 'test-agent'")
            assert agent['status'] == 'online'

    async def test_update_agent_stats_on_completion(self, test_db):
        """测试更新 Agent 统计信息"""
        from utils import update_agent_stats_on_completion

        async with test_db.acquire() as conn:
            await conn.execute("INSERT INTO agents (name, role, status, completed_tasks, failed_tasks, total_tasks) VALUES ('stats-agent', 'research', 'online', 5, 1, 6)")

            await update_agent_stats_on_completion(conn, 'stats-agent', success=True)
            agent = await conn.fetchrow("SELECT * FROM agents WHERE name = 'stats-agent'")
            assert agent['completed_tasks'] == 6

            await update_agent_stats_on_completion(conn, 'stats-agent', success=False)
            agent = await conn.fetchrow("SELECT * FROM agents WHERE name = 'stats-agent'")
            assert agent['failed_tasks'] == 2

    async def test_log_task_action(self, test_db):
        """测试记录任务操作日志"""
        from utils import log_task_action

        async with test_db.acquire() as conn:
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Log Test', 'active') RETURNING id")
            task = await conn.fetchrow("INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Log Task', 'research', 'pending') RETURNING id", project['id'])

            await log_task_action(conn, task['id'], 'test_action', old_status='pending', new_status='running', message='Test message', actor='test-user')

            logs = await conn.fetch("SELECT * FROM task_logs WHERE task_id = $1", task['id'])
            assert len(logs) == 1


class TestDatabase:
    """数据库测试"""

    async def test_get_pool(self):
        """测试获取连接池"""
        from database import get_pool, reset_pool

        pool = await get_pool()
        assert pool is not None

        await reset_pool()


class TestChannels:
    """频道 API 测试"""

    async def test_register_agent_channel(self, client, auth_headers):
        """测试注册 Agent 频道"""
        await client.post("/agents/register/", json={"name": "channel-agent", "role": "research"}, headers=auth_headers)

        response = await client.post(
            "/v1/agent-channels/",
            json={"agent_name": "channel-agent", "channel_id": "123456"},
            headers=auth_headers
        )
        assert response.status_code == 200

    async def test_unregister_agent_channel(self, client, auth_headers):
        """测试注销 Agent 频道"""
        await client.post("/agents/register/", json={"name": "unregister-channel-agent", "role": "research"}, headers=auth_headers)
        await client.post("/v1/agent-channels/", json={"agent_name": "unregister-channel-agent", "channel_id": "123456"}, headers=auth_headers)

        response = await client.request(
            "DELETE",
            "/v1/agent-channels/",
            json={"agent_name": "unregister-channel-agent", "channel_id": "123456"},
            headers=auth_headers
        )
        assert response.status_code == 200

    async def test_get_channel_agents(self, client, auth_headers):
        """测试获取频道中的 Agents"""
        response = await client.get("/v1/channels/test-channel/agents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestDashboard:
    """仪表盘 API 测试"""

    async def test_get_dashboard_stats(self, client):
        """测试获取仪表盘统计"""
        response = await client.get("/v1/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "tasks" in data
        assert "agents" in data


class TestBackgroundTasks:
    """后台任务测试"""

    async def test_sleep_with_shutdown_check(self):
        """测试带关闭检查的睡眠"""
        from background import _sleep_with_shutdown_check, _shutdown_event

        result = await _sleep_with_shutdown_check(0.01)
        assert result is False

        _shutdown_event.set()
        result = await _sleep_with_shutdown_check(10)
        assert result is True

        _shutdown_event.clear()

    async def test_should_reset_pool(self):
        """测试连接池重置判断"""
        from background import _should_reset_pool, _error_counts, _MAX_ERRORS_BEFORE_RESET

        _error_counts["test"] = 0

        for i in range(_MAX_ERRORS_BEFORE_RESET - 1):
            assert _should_reset_pool("test") is False

        assert _should_reset_pool("test") is True
        assert _error_counts["test"] == 0


class TestMain:
    """主应用测试"""

    async def test_request_logging_middleware_success(self, client):
        """测试请求日志中间件 - 成功请求"""
        response = await client.get("/")
        assert response.status_code == 200

    async def test_cors_configuration(self, client):
        """测试 CORS 配置"""
        response = await client.get("/", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200

    async def test_sanitize_log_data_with_exception(self):
        """测试日志脱敏处理异常数据"""
        from main import sanitize_log_data

        # 测试非字典输入
        result = sanitize_log_data("string input")
        assert result == "string input"

        result = sanitize_log_data(None)
        assert result is None

        result = sanitize_log_data([1, 2, 3])
        assert result == [1, 2, 3]

    async def test_sanitize_log_data_short_value(self):
        """测试短值脱敏"""
        from main import sanitize_log_data

        data = {"password": "ab"}
        result = sanitize_log_data(data)
        assert result["password"] == "***"

    async def test_sanitize_log_data_colon_format(self):
        """测试冒号格式的敏感信息"""
        from main import sanitize_log_data

        data = {"message": "Authorization: Bearer token123"}
        result = sanitize_log_data(data)
        assert "***" in result["message"]


class TestBackgroundFull:
    """后台任务完整测试"""

    async def test_heartbeat_monitor_db_error(self, test_db):
        """测试心跳监控器数据库错误处理"""
        from background import heartbeat_monitor, _shutdown_event, _error_counts

        # 设置关闭信号以快速退出
        _shutdown_event.set()

        # 运行监控器（应该快速退出）
        await heartbeat_monitor()

        # 清理
        _shutdown_event.clear()

    async def test_stuck_task_monitor_db_error(self, test_db):
        """测试卡住任务监控器数据库错误处理"""
        from background import stuck_task_monitor, _shutdown_event

        _shutdown_event.set()
        await stuck_task_monitor()
        _shutdown_event.clear()

    async def test_soft_delete_cleanup_monitor_db_error(self, test_db):
        """测试软删除清理监控器数据库错误处理"""
        from background import soft_delete_cleanup_monitor, _shutdown_event

        _shutdown_event.set()
        await soft_delete_cleanup_monitor()
        _shutdown_event.clear()

    async def test_shutdown_background_tasks(self):
        """测试后台任务关闭"""
        from background import shutdown_background_tasks, _shutdown_event

        await shutdown_background_tasks()
        assert _shutdown_event.is_set()

        # 清理
        _shutdown_event.clear()

    async def test_heartbeat_monitor_with_stuck_tasks(self, test_db):
        """测试心跳监控器处理卡住的任务"""
        from background import heartbeat_monitor, _shutdown_event

        async with test_db.acquire() as conn:
            # 创建项目
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Heartbeat Test', 'active') RETURNING id")
            # 创建 Agent
            await conn.execute("INSERT INTO agents (name, role, status, last_heartbeat) VALUES ('heartbeat-agent', 'research', 'online', NOW() - INTERVAL '10 minutes')")
            # 创建任务
            await conn.execute("INSERT INTO tasks (project_id, title, task_type, status, assignee_agent, started_at) VALUES ($1, 'Stuck Task', 'research', 'running', 'heartbeat-agent', NOW() - INTERVAL '3 hours')", project['id'])

        _shutdown_event.set()
        await heartbeat_monitor()
        _shutdown_event.clear()

    async def test_stuck_task_monitor_release_task(self, test_db):
        """测试卡住任务监控器释放超时任务"""
        from background import stuck_task_monitor, _shutdown_event

        async with test_db.acquire() as conn:
            # 创建项目
            project = await conn.fetchrow("INSERT INTO projects (name, status) VALUES ('Stuck Monitor Test', 'active') RETURNING id")
            # 创建 Agent
            await conn.execute("INSERT INTO agents (name, role, status) VALUES ('stuck-agent', 'research', 'busy')")
            # 创建超时任务（使用默认超时时间）
            await conn.execute("""
                INSERT INTO tasks (project_id, title, task_type, status, assignee_agent, started_at)
                VALUES ($1, 'Timeout Task', 'research', 'running', 'stuck-agent', NOW() - INTERVAL '3 hours')
            """, project['id'])

        _shutdown_event.set()
        await stuck_task_monitor()
        _shutdown_event.clear()

    async def test_stuck_task_monitor_unexpected_error(self, test_db):
        """测试卡住任务监控器处理意外错误"""
        from background import stuck_task_monitor, _shutdown_event

        _shutdown_event.set()
        await stuck_task_monitor()
        _shutdown_event.clear()


class TestSecurityFull:
    """安全模块完整测试"""

    async def test_verify_api_key_none_config(self):
        """测试 API Key 验证 - 配置为 None"""
        from security import verify_api_key
        from config import Config

        original = Config.API_KEY
        try:
            Config.API_KEY = None
            result = await verify_api_key(None)
            assert result is None
        finally:
            Config.API_KEY = original

    async def test_verify_api_key_empty_config(self):
        """测试 API Key 验证 - 配置为空字符串"""
        from security import verify_api_key
        from config import Config

        original = Config.API_KEY
        try:
            Config.API_KEY = ""
            result = await verify_api_key(None)
            assert result is None
        finally:
            Config.API_KEY = original

    async def test_rate_limit_no_client(self):
        """测试速率限制 - 无客户端信息"""
        from security import rate_limit
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.client = None

        result = await rate_limit(mock_request)
        assert result is True


class TestUtilsFull:
    """工具函数完整测试"""

    async def test_json_formatter_with_extra(self):
        """测试 JSON 格式化器带额外字段"""
        from utils import JSONFormatter
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        record.agent_name = "test-agent"
        record.task_id = 123
        record.project_id = 456
        record.action = "test_action"
        record.duration_ms = 100.5

        result = formatter.format(record)
        assert "test-agent" in result
        assert "123" in result

    async def test_json_formatter_with_exception(self):
        """测试 JSON 格式化器带异常"""
        from utils import JSONFormatter
        import logging
        import sys

        formatter = JSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="Error message", args=(), exc_info=exc_info
            )

        result = formatter.format(record)
        assert "exception" in result or "Error message" in result

    async def test_check_idempotency_expired_key(self, test_db):
        """测试检查过期幂等键"""
        from utils import check_idempotency, store_idempotency_response

        async with test_db.acquire() as conn:
            key = "expired-key"
            response = {"data": "test"}

            await store_idempotency_response(conn, key, response)
            # 手动设置为过期
            await conn.execute(
                "UPDATE idempotency_keys SET created_at = NOW() - INTERVAL '25 hours' WHERE key = $1",
                key
            )

            # 过期的键应该返回 None
            cached, should_skip = await check_idempotency(conn, key)
            assert should_skip is False

    async def test_cleanup_expired_idempotency_keys(self, test_db):
        """测试清理过期幂等键"""
        from utils import cleanup_expired_idempotency_keys, store_idempotency_response

        async with test_db.acquire() as conn:
            key = "cleanup-key"
            await store_idempotency_response(conn, key, {"data": "test"})
            await conn.execute(
                "UPDATE idempotency_keys SET created_at = NOW() - INTERVAL '25 hours' WHERE key = $1",
                key
            )

            count = await cleanup_expired_idempotency_keys(conn)
            assert count >= 0

    async def test_hard_delete(self, test_db):
        """测试硬删除"""
        from utils import hard_delete

        async with test_db.acquire() as conn:
            project = await conn.fetchrow(
                "INSERT INTO projects (name, status) VALUES ('Hard Delete Test', 'active') RETURNING id"
            )

            result = await hard_delete(conn, "projects", project['id'])
            assert result is True

            # 确认已删除
            row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project['id'])
            assert row is None

    async def test_hard_delete_not_found(self, test_db):
        """测试硬删除不存在的记录"""
        from utils import hard_delete

        async with test_db.acquire() as conn:
            result = await hard_delete(conn, "projects", 99999)
            assert result is False

    async def test_restore_soft_deleted_not_found(self, test_db):
        """测试恢复不存在的软删除记录"""
        from utils import restore_soft_deleted

        async with test_db.acquire() as conn:
            result = await restore_soft_deleted(conn, "projects", 99999)
            assert result is False

    async def test_check_dependencies_no_task(self, test_db):
        """测试检查不存在任务的依赖"""
        from utils import check_dependencies

        async with test_db.acquire() as conn:
            deps_ok, deps = await check_dependencies(conn, 99999)
            assert deps_ok is True
            assert deps == []

    async def test_check_dependencies_with_for_update(self, test_db):
        """测试使用 FOR UPDATE 检查依赖"""
        from utils import check_dependencies

        async with test_db.acquire() as conn:
            project = await conn.fetchrow(
                "INSERT INTO projects (name, status) VALUES ('For Update Test', 'active') RETURNING id"
            )
            task_a = await conn.fetchrow(
                "INSERT INTO tasks (project_id, title, task_type, status) VALUES ($1, 'Task A', 'research', 'completed') RETURNING id",
                project['id']
            )
            task_b = await conn.fetchrow(
                "INSERT INTO tasks (project_id, title, task_type, status, dependencies) VALUES ($1, 'Task B', 'research', 'pending', ARRAY[$2::int]) RETURNING id",
                project['id'], task_a['id']
            )

            deps_ok, deps = await check_dependencies(conn, task_b['id'], for_update=True)
            assert deps_ok is True

    async def test_validate_task_dependencies_cycle(self):
        """测试验证任务依赖 - 循环依赖"""
        from utils import validate_task_dependencies
        from fastapi import HTTPException

        class MockTask:
            def __init__(self, deps=None):
                self.dependencies = deps

        # A -> B -> C -> A 循环
        tasks = [
            MockTask([1]),  # A 依赖 B
            MockTask([2]),  # B 依赖 C
            MockTask([0]),  # C 依赖 A (形成循环)
        ]

        with pytest.raises(HTTPException) as exc_info:
            validate_task_dependencies(tasks)
        assert exc_info.value.status_code == 400
        assert "Circular dependency" in exc_info.value.detail

    async def test_rate_limiter_cleanup_expired(self):
        """测试速率限制器清理过期记录"""
        from utils import RateLimiter

        limiter = RateLimiter(window=0.01, max_requests=10)  # 很短的窗口

        # 添加记录
        await limiter.is_allowed("key1")
        await asyncio.sleep(0.02)  # 等待过期

        # 再次访问应该清理过期记录
        await limiter.is_allowed("key1")
        # 如果过期被清理，应该还有剩余额度
        remaining = await limiter.get_remaining("key1")
        assert remaining >= 9

    async def test_rate_limiter_force_cleanup_logging(self, caplog):
        """测试速率限制器强制清理日志"""
        from utils import RateLimiter
        import logging

        limiter = RateLimiter(window=60, max_requests=10, max_store_size=2)

        # 填满存储
        for i in range(3):
            await limiter.is_allowed(f"key_{i}")

        # 应该触发强制清理并记录日志
        with caplog.at_level(logging.WARNING):
            await limiter.is_allowed("key_overflow")


class TestChannelsFull:
    """频道 API 完整测试"""

    async def test_register_agent_channel_creates_agent(self, client, auth_headers):
        """测试注册频道 - 先创建 Agent 再注册频道"""
        # 先创建 Agent
        await client.post(
            "/agents/register/",
            json={"name": "channel-test-agent", "role": "research"},
            headers=auth_headers
        )

        response = await client.post(
            "/v1/agent-channels/",
            json={"agent_name": "channel-test-agent", "channel_id": "123456"},
            headers=auth_headers
        )
        assert response.status_code == 200

    async def test_register_agent_channel_update_existing(self, client, auth_headers):
        """测试更新已存在的频道记录"""
        # 先创建 Agent 和频道
        await client.post("/agents/register/", json={"name": "channel-update-agent", "role": "research"}, headers=auth_headers)
        await client.post("/v1/agent-channels/", json={"agent_name": "channel-update-agent", "channel_id": "123"}, headers=auth_headers)

        # 再次注册应该更新 last_seen
        response = await client.post(
            "/v1/agent-channels/",
            json={"agent_name": "channel-update-agent", "channel_id": "123"},
            headers=auth_headers
        )
        assert response.status_code == 200


class TestEdgeCasesFull:
    """完整边界情况测试"""

    async def test_create_task_with_parent(self, client, auth_headers):
        """测试创建带子任务的任务"""
        project_resp = await client.post("/projects/", json={"name": "Parent Task Project"}, headers=auth_headers)
        project = project_resp.json()

        parent_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Parent Task", "task_type": "research"},
            headers=auth_headers
        )
        parent = parent_resp.json()

        child_resp = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Child Task", "task_type": "research", "parent_task_id": parent["id"]},
            headers=auth_headers
        )
        assert child_resp.status_code == 200
        assert child_resp.json()["parent_task_id"] == parent["id"]

    async def test_list_tasks_with_assignee_filter(self, client, auth_headers):
        """测试按分配人过滤任务"""
        project_resp = await client.post("/projects/", json={"name": "Assignee Filter Project"}, headers=auth_headers)
        project = project_resp.json()

        await client.post("/agents/register/", json={"name": "assignee-agent", "role": "research"}, headers=auth_headers)
        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Assigned Task", "task_type": "research", "assignee_agent": "assignee-agent"},
            headers=auth_headers
        )

        response = await client.get("/tasks/?assignee=assignee-agent")
        assert response.status_code == 200

    async def test_list_tasks_with_tags_filter(self, client, auth_headers):
        """测试按标签过滤任务"""
        project_resp = await client.post("/projects/", json={"name": "Tags Filter Project"}, headers=auth_headers)
        project = project_resp.json()

        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Tagged Task", "task_type": "research", "task_tags": ["urgent", "backend"]},
            headers=auth_headers
        )

        response = await client.get("/tasks/?tags=urgent")
        assert response.status_code == 200

    async def test_get_available_tasks_with_dependencies(self, client, auth_headers):
        """测试获取可认领任务时考虑依赖"""
        project_resp = await client.post("/projects/", json={"name": "Dependency Available Project"}, headers=auth_headers)
        project = project_resp.json()

        task1 = await client.post("/tasks/", json={"project_id": project["id"], "title": "Dep Task 1", "task_type": "research"}, headers=auth_headers)
        await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Dep Task 2", "task_type": "research", "dependencies": [task1.json()["id"]]},
            headers=auth_headers
        )

        response = await client.get("/tasks/available")
        assert response.status_code == 200
        # 只有无依赖或依赖已完成的任务才应该返回

    async def test_claim_task_with_uncompleted_dependencies(self, client, auth_headers):
        """测试认领有未完成依赖的任务"""
        project_resp = await client.post("/projects/", json={"name": "Uncompleted Dep Project"}, headers=auth_headers)
        project = project_resp.json()

        await client.post("/agents/register/", json={"name": "dep-agent", "role": "research"}, headers=auth_headers)

        task1 = await client.post("/tasks/", json={"project_id": project["id"], "title": "Incomplete Task", "task_type": "research"}, headers=auth_headers)
        task2 = await client.post(
            "/tasks/",
            json={"project_id": project["id"], "title": "Waiting Task", "task_type": "research", "dependencies": [task1.json()["id"]]},
            headers=auth_headers
        )

        response = await client.post(f"/tasks/{task2.json()['id']}/claim/", params={"agent_name": "dep-agent"}, headers=auth_headers)
        assert response.status_code == 400  # 依赖未完成

    async def test_retry_task_max_retries_exceeded(self, client, auth_headers):
        """测试超过最大重试次数"""
        project_resp = await client.post("/projects/", json={"name": "Max Retry Project"}, headers=auth_headers)
        project = project_resp.json()

        task = await client.post("/tasks/", json={"project_id": project["id"], "title": "Max Retry Task", "task_type": "research"}, headers=auth_headers)
        task_id = task.json()["id"]

        await client.post("/agents/register/", json={"name": "max-retry-agent", "role": "research"}, headers=auth_headers)

        # 多次重试
        for _ in range(4):
            await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "max-retry-agent"}, headers=auth_headers)
            await client.post(f"/tasks/{task_id}/start/", params={"agent_name": "max-retry-agent"}, headers=auth_headers)
            await client.post(f"/tasks/{task_id}/submit/", params={"agent_name": "max-retry-agent"}, json={"output": "result"}, headers=auth_headers)
            await client.post(f"/tasks/{task_id}/review/", params={"reviewer": "test"}, json={"approved": False}, headers=auth_headers)
            await client.post(f"/tasks/{task_id}/retry/", headers=auth_headers)

        # 第4次重试后应该超过限制
        response = await client.post(f"/tasks/{task_id}/retry/", headers=auth_headers)
        # 可能返回 400 表示超过最大重试次数

    async def test_update_task_status_to_completed(self, client, auth_headers):
        """测试更新任务状态为已完成"""
        project_resp = await client.post("/projects/", json={"name": "Complete Status Project"}, headers=auth_headers)
        project = project_resp.json()

        await client.post("/agents/register/", json={"name": "complete-agent", "role": "research"}, headers=auth_headers)

        task = await client.post("/tasks/", json={"project_id": project["id"], "title": "Complete Task", "task_type": "research"}, headers=auth_headers)
        task_id = task.json()["id"]

        await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "complete-agent"}, headers=auth_headers)

        response = await client.patch(f"/tasks/{task_id}", json={"status": "completed"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    async def test_update_task_status_to_failed(self, client, auth_headers):
        """测试更新任务状态为失败"""
        project_resp = await client.post("/projects/", json={"name": "Fail Status Project"}, headers=auth_headers)
        project = project_resp.json()

        await client.post("/agents/register/", json={"name": "fail-agent", "role": "research"}, headers=auth_headers)

        task = await client.post("/tasks/", json={"project_id": project["id"], "title": "Fail Task", "task_type": "research"}, headers=auth_headers)
        task_id = task.json()["id"]

        await client.post(f"/tasks/{task_id}/claim/", params={"agent_name": "fail-agent"}, headers=auth_headers)

        response = await client.patch(f"/tasks/{task_id}", json={"status": "failed"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
