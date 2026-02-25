"""
Task Service 测试套件

运行方式:
    pytest tests/ -v

需要环境变量:
    DATABASE_URL=postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test
"""

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 设置测试环境
os.environ["DATABASE_URL"] = "postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test"
os.environ["API_KEY"] = "test-api-key"
os.environ["LOG_LEVEL"] = "DEBUG"

import asyncpg

from main import app, get_db

# ============ 数据库初始化 ============

async def init_test_database():
    """初始化测试数据库（只运行一次）"""
    admin_url = "postgresql://taskmanager:taskmanager@localhost:5433/postgres"
    test_db_url = "postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test"

    # 连接到 postgres 数据库创建测试数据库
    conn = await asyncpg.connect(admin_url)
    try:
        # 终止现有连接
        await conn.execute("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = 'taskmanager_test'
            AND pid <> pg_backend_pid()
        """)
        await conn.execute("DROP DATABASE IF EXISTS taskmanager_test")
        await conn.execute("CREATE DATABASE taskmanager_test")
    finally:
        await conn.close()

    # 连接到测试数据库并执行 schema
    conn = await asyncpg.connect(test_db_url)
    try:
        with open("schema.sql") as f:
            schema = f.read()
            await conn.execute(schema)
    finally:
        await conn.close()


# 在导入时初始化数据库
asyncio.run(init_test_database())


# ============ Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_db():
    """每个测试使用独立的数据库连接池"""
    test_db_url = "postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test"

    # 创建连接池
    pool = await asyncpg.create_pool(test_db_url, min_size=1, max_size=5)

    yield pool

    # 清理数据
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE task_logs, tasks, agents, projects, agent_channels, idempotency_keys RESTART IDENTITY CASCADE")

    await pool.close()


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """创建测试客户端"""
    # 覆盖 get_db 使用测试连接池
    async def override_get_db():
        return test_db

    app.dependency_overrides[get_db] = override_get_db

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

    async def test_list_projects(self, client):
        """测试列出项目"""
        response = await client.get("/projects/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_project(self, client, auth_headers):
        """测试获取项目详情"""
        # 先创建项目
        create_resp = await client.post(
            "/projects/",
            json={"name": "Get Test Project"},
            headers=auth_headers
        )
        project = create_resp.json()

        # 获取项目
        response = await client.get(f"/projects/{project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project["id"]

    async def test_get_project_not_found(self, client):
        """测试获取不存在的项目"""
        response = await client.get("/projects/99999")
        assert response.status_code == 404


class TestTasks:
    """任务 API 测试"""

    async def test_create_task(self, client, auth_headers):
        """测试创建任务"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Task Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 创建任务
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


class TestAgents:
    """Agent API 测试"""

    async def test_register_agent(self, client, auth_headers):
        """测试注册 Agent"""
        response = await client.post(
            "/agents/register/",
            json={
                "name": "test-agent-1",
                "role": "research",
                "skills": ["python", "data-analysis"]
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-agent-1"
        assert data["status"] == "online"


class TestTaskLifecycle:
    """任务完整生命周期测试"""

    async def test_full_task_lifecycle_success(self, client, auth_headers):
        """测试完整任务流转：pending → assigned → running → reviewing → completed"""
        # 1. 创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Lifecycle Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 2. 创建任务
        task_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Lifecycle Test Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task = task_resp.json()
        task_id = task["id"]

        # 3. 注册 Agent
        await client.post(
            "/agents/register/",
            json={"name": "lifecycle-agent", "role": "research"},
            headers=auth_headers
        )

        # 4. 认领任务 (pending → assigned)
        claim_resp = await client.post(
            f"/tasks/{task_id}/claim/",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert claim_resp.status_code == 200
        assert claim_resp.json()["status"] == "assigned"

        # 5. 开始任务 (assigned → running)
        start_resp = await client.post(
            f"/tasks/{task_id}/start/",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "running"

        # 6. 提交任务 (running → reviewing)
        submit_resp = await client.post(
            f"/tasks/{task_id}/submit/",
            params={"agent_name": "lifecycle-agent"},
            json={"output": "test result", "summary": "Task completed successfully"},
            headers=auth_headers
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "reviewing"

        # 7. 验收通过 (reviewing → completed)
        review_resp = await client.post(
            f"/tasks/{task_id}/review/",
            params={"reviewer": "test-reviewer"},
            json={"approved": True, "feedback": "Good job!"},
            headers=auth_headers
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
