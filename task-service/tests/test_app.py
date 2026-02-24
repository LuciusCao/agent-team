"""
Task Service 测试套件

运行方式:
    pytest tests/ -v
    pytest tests/ -v --cov=app

需要环境变量:
    TEST_DATABASE_URL=postgresql://test:test@localhost:5432/test_taskmanager
"""

import os
import pytest
import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport

# 设置测试数据库
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://taskmanager:taskmanager@localhost:5432/taskmanager_test"
)
os.environ["API_KEY"] = "test-api-key"
os.environ["LOG_LEVEL"] = "DEBUG"

from app import app, get_db, pool


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db():
    """创建测试数据库连接池"""
    import asyncpg
    
    # 连接到测试数据库并初始化 schema
    db_url = os.environ["DATABASE_URL"]
    
    # 先连接到默认数据库创建测试数据库
    default_url = db_url.replace("taskmanager_test", "taskmanager")
    conn = await asyncpg.connect(default_url)
    
    try:
        await conn.execute("DROP DATABASE IF EXISTS taskmanager_test")
        await conn.execute("CREATE DATABASE taskmanager_test")
    except:
        pass
    finally:
        await conn.close()
    
    # 连接到测试数据库并执行 schema
    test_conn = await asyncpg.connect(db_url)
    
    with open("schema.sql", "r") as f:
        schema = f.read()
        await test_conn.execute(schema)
    
    await test_conn.close()
    
    # 创建连接池
    test_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    
    yield test_pool
    
    await test_pool.close()


@pytest.fixture
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
async def auth_headers():
    """认证头"""
    return {"X-API-Key": "test-api-key"}


class TestHealth:
    """健康检查测试"""
    
    async def test_root(self, client):
        """测试根路径"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestProjects:
    """项目 API 测试"""
    
    async def test_create_project(self, client, auth_headers):
        """测试创建项目"""
        response = await client.post(
            "/projects",
            json={"name": "Test Project", "description": "Test description"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "Test description"
        assert "id" in data
    
    async def test_list_projects(self, client):
        """测试列出项目"""
        response = await client.get("/projects")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    async def test_get_project(self, client, auth_headers):
        """测试获取项目详情"""
        # 先创建项目
        create_resp = await client.post(
            "/projects",
            json={"name": "Get Test Project"},
            headers=auth_headers
        )
        project = create_resp.json()
        
        # 获取项目
        response = await client.get(f"/projects/{project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project["id"]
        assert data["name"] == "Get Test Project"
    
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
            "/projects",
            json={"name": "Task Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        # 创建任务
        response = await client.post(
            "/tasks",
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
    
    async def test_create_task_with_timeout(self, client, auth_headers):
        """测试创建带超时的任务"""
        # 先创建项目
        project_resp = await client.post(
            "/projects",
            json={"name": "Timeout Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        # 创建带超时的任务
        response = await client.post(
            "/tasks",
            json={
                "project_id": project["id"],
                "title": "Timeout Task",
                "task_type": "research",
                "timeout_minutes": 60
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["timeout_minutes"] == 60
    
    async def test_claim_task(self, client, auth_headers):
        """测试认领任务"""
        # 创建项目和任务
        project_resp = await client.post(
            "/projects",
            json={"name": "Claim Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks",
            json={
                "project_id": project["id"],
                "title": "Claimable Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task = task_resp.json()
        
        # 注册 Agent
        await client.post(
            "/agents/register",
            json={"name": "test-agent", "role": "research"},
            headers=auth_headers
        )
        
        # 认领任务
        response = await client.post(
            f"/tasks/{task['id']}/claim",
            params={"agent_name": "test-agent"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "assigned"
        assert data["assignee_agent"] == "test-agent"
    
    async def test_claim_task_unauthorized(self, client):
        """测试未认证认领任务"""
        response = await client.post(
            "/tasks/1/claim",
            params={"agent_name": "test-agent"}
        )
        assert response.status_code == 403


class TestIdempotency:
    """幂等性测试"""
    
    async def test_claim_task_idempotent(self, client, auth_headers):
        """测试认领任务幂等性"""
        # 创建项目和任务
        project_resp = await client.post(
            "/projects",
            json={"name": "Idempotency Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks",
            json={
                "project_id": project["id"],
                "title": "Idempotent Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task = task_resp.json()
        
        # 注册 Agent
        await client.post(
            "/agents/register",
            json={"name": "idempotent-agent", "role": "research"},
            headers=auth_headers
        )
        
        # 第一次认领（带幂等键）
        idempotency_key = "test-key-123"
        response1 = await client.post(
            f"/tasks/{task['id']}/claim",
            params={"agent_name": "idempotent-agent", "idempotency_key": idempotency_key},
            headers=auth_headers
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # 第二次认领（相同幂等键）- 应该返回相同结果
        response2 = await client.post(
            f"/tasks/{task['id']}/claim",
            params={"agent_name": "idempotent-agent", "idempotency_key": idempotency_key},
            headers=auth_headers
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # 两次响应应该相同
        assert data1["id"] == data2["id"]
        assert data1["status"] == data2["status"]
    
    async def test_submit_task_idempotent(self, client, auth_headers):
        """测试提交任务幂等性"""
        # 创建项目、任务、Agent
        project_resp = await client.post(
            "/projects",
            json={"name": "Submit Idempotency Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks",
            json={
                "project_id": project["id"],
                "title": "Submit Test Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task = task_resp.json()
        
        await client.post(
            "/agents/register",
            json={"name": "submit-agent", "role": "research"},
            headers=auth_headers
        )
        
        # 认领并开始任务
        await client.post(
            f"/tasks/{task['id']}/claim",
            params={"agent_name": "submit-agent"},
            headers=auth_headers
        )
        await client.post(
            f"/tasks/{task['id']}/start",
            params={"agent_name": "submit-agent"},
            headers=auth_headers
        )
        
        # 第一次提交（带幂等键）
        idempotency_key = "submit-key-456"
        response1 = await client.post(
            f"/tasks/{task['id']}/submit",
            params={"agent_name": "submit-agent", "idempotency_key": idempotency_key},
            json={"output": "test result"},
            headers=auth_headers
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # 第二次提交（相同幂等键）- 应该返回相同结果
        response2 = await client.post(
            f"/tasks/{task['id']}/submit",
            params={"agent_name": "submit-agent", "idempotency_key": idempotency_key},
            json={"output": "different result"},  # 不同内容，但幂等键相同
            headers=auth_headers
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # 两次响应应该相同（第一次的结果）
        assert data1["id"] == data2["id"]
        assert data1["result"] == data2["result"]  # 结果应该是第一次的


class TestAgents:
    """Agent API 测试"""
    
    async def test_register_agent(self, client, auth_headers):
        """测试注册 Agent"""
        response = await client.post(
            "/agents/register",
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
        assert "python" in data["skills"]
    
    async def test_heartbeat(self, client):
        """测试心跳"""
        # 先注册
        await client.post(
            "/agents/register",
            json={"name": "heartbeat-agent", "role": "research"},
            headers={"X-API-Key": "test-api-key"}
        )
        
        # 发送心跳
        response = await client.post(
            "/agents/heartbeat-agent/heartbeat",
            json={"current_task_id": None}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"


class TestRateLimit:
    """速率限制测试"""
    
    async def test_rate_limit(self, client):
        """测试速率限制"""
        # 快速发送多个请求
        for i in range(105):  # 超过 100 的限制
            response = await client.get("/")
        
        # 最后一个应该被限流
        assert response.status_code == 429


class TestAuth:
    """认证测试"""
    
    async def test_missing_api_key(self, client):
        """测试缺少 API Key"""
        response = await client.post(
            "/projects",
            json={"name": "Test"}
        )
        assert response.status_code == 403
    
    async def test_invalid_api_key(self, client):
        """测试无效的 API Key"""
        response = await client.post(
            "/projects",
            json={"name": "Test"},
            headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 403


class TestTimeouts:
    """超时配置测试"""
    
    async def test_task_type_defaults(self, client, auth_headers):
        """测试任务类型默认超时"""
        # 创建项目
        project_resp = await client.post(
            "/projects",
            json={"name": "Timeout Defaults Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        # 创建不同类型任务（不指定超时）
        for task_type in ["research", "video", "review"]:
            response = await client.post(
                "/tasks",
                json={
                    "project_id": project["id"],
                    "title": f"{task_type} task",
                    "task_type": task_type
                },
                headers=auth_headers
            )
            assert response.status_code == 200
            # timeout_minutes 应该为 NULL（使用默认值）
            assert response.json()["timeout_minutes"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
