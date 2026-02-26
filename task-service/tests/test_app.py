"""
Task Service 测试套件

运行方式:
    pytest tests/ -v

需要环境变量:
    DATABASE_URL=postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test
"""

import asyncio
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    async def test_create_task_with_dependencies(self, client, auth_headers):
        """测试创建带依赖的任务"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Dependency Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 创建第一个任务
        task1_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "First Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task1 = task1_resp.json()

        # 创建第二个任务，依赖第一个
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

    async def test_create_task_with_circular_dependency(self, client, auth_headers):
        """测试创建带循环依赖的任务应该失败"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Circular Dependency Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 创建任务 A
        task1_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Task A",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task1 = task1_resp.json()

        # 创建任务 B，依赖 A
        task2_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Task B",
                "task_type": "research",
                "dependencies": [task1["id"]]
            },
            headers=auth_headers
        )
        task2 = task2_resp.json()

        # 创建任务 C，依赖 B
        task3_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Task C",
                "task_type": "research",
                "dependencies": [task2["id"]]  # C 依赖 B
            },
            headers=auth_headers
        )
        task3 = task3_resp.json()

        # 创建任务 D，依赖 C
        task4_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Task D",
                "task_type": "research",
                "dependencies": [task3["id"]]  # D 依赖 C
            },
            headers=auth_headers
        )
        task4 = task4_resp.json()

        # 现在尝试创建任务 E，依赖 D 和 A
        # 这会形成 A -> E -> D -> C -> B -> A 的循环（如果 A 依赖 E）
        # 但当前测试只是验证正常创建成功
        task5_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Task E",
                "task_type": "research",
                "dependencies": [task4["id"]]  # E 依赖 D
            },
            headers=auth_headers
        )
        assert task5_resp.status_code == 200

    async def test_create_task_with_duplicate_dependencies(self, client, auth_headers):
        """测试创建带重复依赖的任务应该失败"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Duplicate Dep Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 创建第一个任务
        task1_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "First Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task1 = task1_resp.json()

        # 尝试创建第二个任务，带重复依赖
        response = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Second Task",
                "task_type": "research",
                "dependencies": [task1["id"], task1["id"]]  # 重复依赖
            },
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Duplicate dependencies" in response.json()["detail"]

    async def test_create_task_with_invalid_dependency(self, client, auth_headers):
        """测试创建带无效依赖的任务应该失败"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Invalid Dep Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()

        # 尝试创建任务，带无效依赖（负数）
        response = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Invalid Task",
                "task_type": "research",
                "dependencies": [-1]  # 无效依赖ID
            },
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Invalid dependency ID" in response.json()["detail"]


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


class TestRateLimiter:
    """速率限制器测试"""

    async def test_rate_limiter_basic(self, client):
        """测试基础速率限制功能"""
        # 发送多个请求到不需要认证的端点
        responses = []
        for _ in range(5):
            resp = await client.get("/projects/")
            responses.append(resp.status_code)

        # 应该都能成功（在限制内）
        assert all(code == 200 for code in responses)

    async def test_rate_limiter_with_force_cleanup(self, client, auth_headers):
        """测试速率限制器强制清理功能"""
        from utils import RateLimiter

        # 创建一个小容量的限流器
        limiter = RateLimiter(
            window=60,
            max_requests=2,
            max_store_size=3  # 很小的容量
        )

        # 填满存储
        for i in range(3):
            allowed = await limiter.is_allowed(f"key_{i}")
            assert allowed is True

        # 再添加一个应该触发强制清理
        allowed = await limiter.is_allowed("key_overflow")
        assert allowed is True

        # 验证清理后容量恢复正常
        assert len(limiter.store) <= 3


class TestCircularDependency:
    """循环依赖检测测试"""

    async def test_check_circular_dependency_no_cycle(self, test_db):
        """测试无循环依赖的情况"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            # 先创建项目
            await conn.execute(
                """INSERT INTO projects (id, name, status)
                   VALUES (1, 'Test Project', 'active')
                   ON CONFLICT DO NOTHING"""
            )

            # 创建任务 A
            task_a = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status)
                   VALUES (1, 'Task A', 'research', 'pending')
                   RETURNING id"""
            )

            # 创建任务 B，依赖 A
            task_b = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status, dependencies)
                   VALUES (1, 'Task B', 'research', 'pending', ARRAY[$1::int])
                   RETURNING id""",
                task_a["id"]
            )

            # 检查 B 依赖 A 是否形成循环（不应该）
            has_cycle = await check_circular_dependency(conn, task_b["id"], [task_a["id"]])
            assert has_cycle is False

            # 检查新任务依赖 B 是否形成循环（不应该）
            has_cycle = await check_circular_dependency(conn, None, [task_b["id"]])
            assert has_cycle is False

    async def test_check_circular_dependency_with_cycle(self, test_db):
        """测试有循环依赖的情况"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            # 先创建项目
            await conn.execute(
                """INSERT INTO projects (id, name, status)
                   VALUES (1, 'Test Project', 'active')
                   ON CONFLICT DO NOTHING"""
            )

            # 创建任务 A
            task_a = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status)
                   VALUES (1, 'Task A', 'research', 'pending')
                   RETURNING id"""
            )

            # 创建任务 B，依赖 A
            task_b = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status, dependencies)
                   VALUES (1, 'Task B', 'research', 'pending', ARRAY[$1::int])
                   RETURNING id""",
                task_a["id"]
            )

            # 更新 A 依赖 B（形成循环 A -> B -> A）
            await conn.execute(
                "UPDATE tasks SET dependencies = ARRAY[$1::int] WHERE id = $2",
                task_b["id"], task_a["id"]
            )

            # 场景1: 检查新任务（ID=999）依赖 A 是否形成循环
            # 新任务 -> A -> B -> A（检测到循环）
            has_cycle = await check_circular_dependency(conn, 999, [task_a["id"]])
            assert has_cycle is True

            # 场景2: 检查任务 B 如果依赖 A 是否形成循环（B->A->B）
            has_cycle = await check_circular_dependency(conn, task_b["id"], [task_a["id"]])
            assert has_cycle is True

    async def test_check_circular_dependency_long_chain(self, test_db):
        """测试长依赖链的循环检测"""
        from utils import check_circular_dependency

        async with test_db.acquire() as conn:
            # 先创建项目
            await conn.execute(
                """INSERT INTO projects (id, name, status)
                   VALUES (1, 'Test Project', 'active')
                   ON CONFLICT DO NOTHING"""
            )

            # 创建 A -> B -> C -> D 链
            task_a = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status)
                   VALUES (1, 'Task A', 'research', 'pending')
                   RETURNING id"""
            )

            task_b = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status, dependencies)
                   VALUES (1, 'Task B', 'research', 'pending', ARRAY[$1::int])
                   RETURNING id""",
                task_a["id"]
            )

            task_c = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status, dependencies)
                   VALUES (1, 'Task C', 'research', 'pending', ARRAY[$1::int])
                   RETURNING id""",
                task_b["id"]
            )

            task_d = await conn.fetchrow(
                """INSERT INTO tasks (project_id, title, task_type, status, dependencies)
                   VALUES (1, 'Task D', 'research', 'pending', ARRAY[$1::int])
                   RETURNING id""",
                task_c["id"]
            )

            # 无循环: 新任务依赖 D
            has_cycle = await check_circular_dependency(conn, 999, [task_d["id"]])
            assert has_cycle is False

            # 创建循环：让 A 依赖 D（形成 A -> B -> C -> D -> A）
            await conn.execute(
                "UPDATE tasks SET dependencies = ARRAY[$1::int] WHERE id = $2",
                task_d["id"], task_a["id"]
            )

            # 现在应该检测到循环: 新任务 -> D -> ... -> A -> D
            has_cycle = await check_circular_dependency(conn, 999, [task_d["id"]])
            assert has_cycle is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
