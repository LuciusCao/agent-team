"""
Task Service 测试套件

运行方式:
    pytest tests/ -v
    pytest tests/ -v --cov=main

需要环境变量:
    TEST_DATABASE_URL=postgresql://test:test@localhost:5432/test_taskmanager
"""

import os
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport

# 设置测试数据库 - 使用 docker-compose 启动的 postgres (端口 5433)
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://taskmanager:taskmanager@localhost:5433/taskmanager"
)
os.environ["API_KEY"] = "test-api-key"
os.environ["LOG_LEVEL"] = "DEBUG"

from main import app, get_db


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """创建测试数据库连接池"""
    import asyncpg
    
    # 使用固定的测试数据库 URL
    test_db_url = "postgresql://taskmanager:taskmanager@localhost:5433/taskmanager_test"
    
    # 创建连接池
    test_pool = await asyncpg.create_pool(test_db_url, min_size=1, max_size=5)
    
    yield test_pool
    
    await test_pool.close()


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
async def auth_headers():
    """认证头"""
    return {"X-API-Key": "test-api-key"}


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
        assert task["status"] == "pending"
        task_id = task["id"]
        
        # 3. 注册 Agent
        await client.post(
            "/agents/register/",
            json={"name": "lifecycle-agent", "role": "research"},
            headers=auth_headers
        )
        
        # 4. 认领任务 (pending → assigned)
        claim_resp = await client.post(
            f"/tasks/{task_id}/claim",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert claim_resp.status_code == 200
        assert claim_resp.json()["status"] == "assigned"
        
        # 5. 开始任务 (assigned → running)
        start_resp = await client.post(
            f"/tasks/{task_id}/start",
            params={"agent_name": "lifecycle-agent"},
            headers=auth_headers
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "running"
        
        # 6. 提交任务 (running → reviewing)
        submit_resp = await client.post(
            f"/tasks/{task_id}/submit",
            params={"agent_name": "lifecycle-agent"},
            json={"output": "test result", "summary": "Task completed successfully"},
            headers=auth_headers
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "reviewing"
        
        # 7. 验收通过 (reviewing → completed)
        review_resp = await client.post(
            f"/tasks/{task_id}/review",
            params={"reviewer": "test-reviewer"},
            json={"approved": True, "feedback": "Good job!"},
            headers=auth_headers
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "completed"
        
        # 8. 验证最终状态
        task_detail = await client.get(f"/tasks/{task_id}")
        assert task_detail.status_code == 200
        final_task = task_detail.json()["task"]
        assert final_task["status"] == "completed"
        assert final_task["assignee_agent"] == "lifecycle-agent"
        assert final_task["completed_at"] is not None
    
    async def test_task_lifecycle_rejected(self, client, auth_headers):
        """测试任务被拒绝流程：pending → assigned → running → reviewing → rejected → pending"""
        # 1. 创建项目和任务
        project_resp = await client.post(
            "/projects/",
            json={"name": "Reject Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Reject Test Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]
        
        # 2. 注册 Agent
        await client.post(
            "/agents/register/",
            json={"name": "reject-agent", "role": "research"},
            headers=auth_headers
        )
        
        # 3. 认领、开始、提交任务
        await client.post(f"/tasks/{task_id}/claim", params={"agent_name": "reject-agent"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/start", params={"agent_name": "reject-agent"}, headers=auth_headers)
        await client.post(
            f"/tasks/{task_id}/submit",
            params={"agent_name": "reject-agent"},
            json={"output": "incomplete work"},
            headers=auth_headers
        )
        
        # 4. 验收拒绝 (reviewing → rejected)
        review_resp = await client.post(
            f"/tasks/{task_id}/review",
            params={"reviewer": "strict-reviewer"},
            json={"approved": False, "feedback": "Need more details"},
            headers=auth_headers
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["status"] == "rejected"
        
        # 5. 重试任务 (rejected → pending)
        retry_resp = await client.post(
            f"/tasks/{task_id}/retry",
            headers=auth_headers
        )
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "pending"
        assert retry_resp.json()["retry_count"] == 1
    
    async def test_cannot_start_without_claim(self, client, auth_headers):
        """测试未认领不能开始任务"""
        # 创建项目、任务、Agent
        project_resp = await client.post("/projects/", json={"name": "No Claim Project"}, headers=auth_headers)
        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project_resp.json()["id"], "title": "No Claim Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]
        
        await client.post("/agents/register/", json={"name": "no-claim-agent", "role": "research"}, headers=auth_headers)
        
        # 尝试直接开始未认领的任务
        response = await client.post(
            f"/tasks/{task_id}/start",
            params={"agent_name": "no-claim-agent"},
            headers=auth_headers
        )
        assert response.status_code == 404
        assert "not assigned to you" in response.json()["detail"]
    
    async def test_cannot_submit_without_start(self, client, auth_headers):
        """测试未开始不能提交任务"""
        # 创建项目、任务、Agent
        project_resp = await client.post("/projects/", json={"name": "No Start Project"}, headers=auth_headers)
        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project_resp.json()["id"], "title": "No Start Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]
        
        await client.post("/agents/register/", json={"name": "no-start-agent", "role": "research"}, headers=auth_headers)
        await client.post(f"/tasks/{task_id}/claim", params={"agent_name": "no-start-agent"}, headers=auth_headers)
        
        # 尝试提交未开始的任务
        response = await client.post(
            f"/tasks/{task_id}/submit",
            params={"agent_name": "no-start-agent"},
            json={"output": "result"},
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Cannot submit task with status: assigned" in response.json()["detail"]
    
    async def test_release_task(self, client, auth_headers):
        """测试释放任务"""
        # 创建项目、任务、Agent
        project_resp = await client.post("/projects/", json={"name": "Release Project"}, headers=auth_headers)
        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project_resp.json()["id"], "title": "Release Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]
        
        await client.post("/agents/register/", json={"name": "release-agent", "role": "research"}, headers=auth_headers)
        
        # 认领任务
        await client.post(f"/tasks/{task_id}/claim", params={"agent_name": "release-agent"}, headers=auth_headers)
        
        # 释放任务
        release_resp = await client.post(
            f"/tasks/{task_id}/release",
            params={"agent_name": "release-agent"},
            headers=auth_headers
        )
        assert release_resp.status_code == 200
        assert release_resp.json()["status"] == "pending"
        assert release_resp.json()["assignee_agent"] is None


class TestTaskDependencies:
    """任务依赖测试"""
    
    async def test_cannot_claim_with_unfinished_deps(self, client, auth_headers):
        """依赖未完成时不能认领"""
        # 创建项目
        project_resp = await client.post("/projects/", json={"name": "Deps Project"}, headers=auth_headers)
        project_id = project_resp.json()["id"]
        
        # 创建两个任务
        task1_resp = await client.post(
            "/tasks/",
            json={"project_id": project_id, "title": "Task 1", "task_type": "research"},
            headers=auth_headers
        )
        task1_id = task1_resp.json()["id"]
        
        task2_resp = await client.post(
            "/tasks/",
            json={"project_id": project_id, "title": "Task 2", "task_type": "research", "dependencies": [task1_id]},
            headers=auth_headers
        )
        task2_id = task2_resp.json()["id"]
        
        # 注册 Agent
        await client.post("/agents/register/", json={"name": "deps-agent", "role": "research"}, headers=auth_headers)
        
        # 尝试认领有依赖的任务（应该失败）
        response = await client.post(
            f"/tasks/{task2_id}/claim",
            params={"agent_name": "deps-agent"},
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Dependencies not completed" in response.json()["detail"]
        
        # 完成第一个任务
        await client.post(f"/tasks/{task1_id}/claim", params={"agent_name": "deps-agent"}, headers=auth_headers)
        await client.post(f"/tasks/{task1_id}/start", params={"agent_name": "deps-agent"}, headers=auth_headers)
        await client.post(f"/tasks/{task1_id}/submit", params={"agent_name": "deps-agent"}, json={"output": "done"}, headers=auth_headers)
        await client.post(f"/tasks/{task1_id}/review", params={"reviewer": "test"}, json={"approved": True}, headers=auth_headers)
        
        # 现在可以认领第二个任务
        response = await client.post(
            f"/tasks/{task2_id}/claim",
            params={"agent_name": "deps-agent"},
            headers=auth_headers
        )
        assert response.status_code == 200
    
    async def test_circular_dependencies_detection(self, client, auth_headers):
        """测试循环依赖检测"""
        project_resp = await client.post("/projects/", json={"name": "Circular Project"}, headers=auth_headers)
        project_id = project_resp.json()["id"]
        
        # 尝试创建循环依赖的任务
        response = await client.post(
            f"/projects/{project_id}/breakdown",
            json=[
                {"title": "Task A", "task_type": "research", "dependencies": [1]},  # 依赖 B
                {"title": "Task B", "task_type": "research", "dependencies": [0]},  # 依赖 A（循环！）
            ],
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "Circular dependency detected" in response.json()["detail"]


class TestConcurrency:
    """并发测试"""
    
    async def test_claim_race_condition(self, client, auth_headers):
        """测试认领竞态条件 - 只有一个 Agent 能成功"""
        # 创建项目和一个任务
        project_resp = await client.post("/projects/", json={"name": "Race Project"}, headers=auth_headers)
        task_resp = await client.post(
            "/tasks/",
            json={"project_id": project_resp.json()["id"], "title": "Race Task", "task_type": "research"},
            headers=auth_headers
        )
        task_id = task_resp.json()["id"]
        
        # 注册两个 Agent
        await client.post("/agents/register/", json={"name": "agent-a", "role": "research"}, headers=auth_headers)
        await client.post("/agents/register/", json={"name": "agent-b", "role": "research"}, headers=auth_headers)
        
        # 同时发送两个认领请求
        import asyncio
        
        async def claim_agent_a():
            return await client.post(
                f"/tasks/{task_id}/claim",
                params={"agent_name": "agent-a"},
                headers=auth_headers
            )
        
        async def claim_agent_b():
            return await client.post(
                f"/tasks/{task_id}/claim",
                params={"agent_name": "agent-b"},
                headers=auth_headers
            )
        
        # 并发执行
        results = await asyncio.gather(claim_agent_a(), claim_agent_b(), return_exceptions=True)
        
        # 一个成功，一个失败
        success_count = sum(1 for r in results if hasattr(r, 'status_code') and r.status_code == 200)
        conflict_count = sum(1 for r in results if hasattr(r, 'status_code') and r.status_code == 409)
        
        assert success_count == 1, f"Expected 1 success, got {success_count}"
        assert conflict_count == 1, f"Expected 1 conflict, got {conflict_count}"


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
            "/projects/",
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
    
    async def test_create_task_with_timeout(self, client, auth_headers):
        """测试创建带超时的任务"""
        # 先创建项目
        project_resp = await client.post(
            "/projects/",
            json={"name": "Timeout Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        # 创建带超时的任务
        response = await client.post(
            "/tasks/",
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
            "/projects/",
            json={"name": "Claim Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks/",
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
            "/agents/register/",
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
            "/projects/",
            json={"name": "Idempotency Test Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks/",
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
            "/agents/register/",
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
            "/projects/",
            json={"name": "Submit Idempotency Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        task_resp = await client.post(
            "/tasks/",
            json={
                "project_id": project["id"],
                "title": "Submit Test Task",
                "task_type": "research"
            },
            headers=auth_headers
        )
        task = task_resp.json()
        
        await client.post(
            "/agents/register/",
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
        assert "python" in data["skills"]
    
    async def test_heartbeat(self, client):
        """测试心跳"""
        # 先注册
        await client.post(
            "/agents/register/",
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
            "/projects/",
            json={"name": "Test"}
        )
        assert response.status_code == 403
    
    async def test_invalid_api_key(self, client):
        """测试无效的 API Key"""
        response = await client.post(
            "/projects/",
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
            "/projects/",
            json={"name": "Timeout Defaults Project"},
            headers=auth_headers
        )
        project = project_resp.json()
        
        # 创建不同类型任务（不指定超时）
        for task_type in ["research", "video", "review"]:
            response = await client.post(
                "/tasks/",
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
