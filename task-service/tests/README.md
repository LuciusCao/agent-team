# Task Service 测试

## 运行测试

### 安装依赖

```bash
cd task-service
pip install pytest pytest-asyncio httpx pytest-cov
```

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行特定测试

```bash
# 只测试项目 API
pytest tests/test_app.py::TestProjects -v

# 只测试任务生命周期
pytest tests/test_app.py::TestTaskLifecycle -v

# 只测试任务依赖
pytest tests/test_app.py::TestTaskDependencies -v

# 只测试认证
pytest tests/test_app.py::TestAuth -v

# 只测试并发场景
pytest tests/test_app.py::TestConcurrency -v
```

### 带覆盖率报告

```bash
pytest tests/ --cov=app --cov-report=html
```

### 并行运行测试（加速）

```bash
pip install pytest-xdist
pytest tests/ -v -n auto
```

## 测试环境

测试使用独立的数据库 `taskmanager_test`，会自动：
1. 创建测试数据库
2. 执行 schema.sql 初始化
3. 运行测试
4. 测试结束后保留数据（方便调试）

## 测试分类

| 测试类 | 描述 | 优先级 |
|--------|------|--------|
| `TestHealth` | 健康检查 | 高 |
| `TestProjects` | 项目 CRUD | 高 |
| `TestTasks` | 任务 CRUD、认领 | 高 |
| `TestTaskLifecycle` | 完整任务状态流转 | 高 |
| `TestTaskDependencies` | 任务依赖检查 | 高 |
| `TestCircularDependency` | 循环依赖检测 | 高 |
| `TestRateLimiter` | 速率限制器 | 中 |
| `TestAgents` | Agent 注册 | 中 |
| `TestAuth` | API 认证 | 高 |

## 测试覆盖范围

### 任务生命周期测试 (TestTaskLifecycle)

覆盖完整的任务状态流转：
- `test_full_task_lifecycle_success`: pending → assigned → running → reviewing → completed

### 任务依赖测试 (TestTasks)

- `test_create_task_with_dependencies`: 创建带依赖的任务
- `test_create_task_with_circular_dependency`: 循环依赖检测（API 层面）
- `test_create_task_with_duplicate_dependencies`: 重复依赖检测
- `test_create_task_with_invalid_dependency`: 无效依赖检测

### 循环依赖检测测试 (TestCircularDependency)

- `test_check_circular_dependency_no_cycle`: 无循环依赖的场景
- `test_check_circular_dependency_with_cycle`: 有循环依赖的场景
- `test_check_circular_dependency_long_chain`: 长依赖链的循环检测
- `test_check_circular_dependency_shared_dependency`: **共享依赖不应被误判为循环**（菱形结构）
- `test_check_circular_dependency_self_reference`: 任务不能依赖自己

### 速率限制器测试 (TestRateLimiter)

- `test_rate_limiter_basic`: 基础限流功能
- `test_rate_limiter_with_force_cleanup`: 强制清理机制（防止内存泄漏）

## 添加新测试

```python
class TestNewFeature:
    async def test_something(self, client, auth_headers):
        """测试新功能"""
        response = await client.post(
            "/new-endpoint",
            json={"key": "value"},
            headers=auth_headers
        )
        assert response.status_code == 200
```

## CI/CD 集成

### GitHub Actions 示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_taskmanager
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio httpx pytest-cov
    
    - name: Run tests
      run: pytest tests/ -v --cov=app --cov-report=xml
      env:
        TEST_DATABASE_URL: postgresql://test:test@localhost:5432/test_taskmanager
        API_KEY: test-api-key
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## 调试技巧

### 查看测试数据库

```bash
# 连接到测试数据库
psql postgresql://taskmanager:taskmanager@localhost:5432/taskmanager_test

# 查看任务
SELECT * FROM tasks ORDER BY created_at DESC;

# 查看 Agent
SELECT * FROM agents;

# 查看日志
SELECT * FROM task_logs ORDER BY created_at DESC LIMIT 10;
```

### 失败的测试保留数据

测试失败后，测试数据库的数据会被保留，方便调试：

```bash
# 查看测试后的状态
psql postgresql://taskmanager:taskmanager@localhost:5432/taskmanager_test -c "SELECT * FROM tasks;"
```

### 使用 pdb 调试

```python
async def test_something(self, client, auth_headers):
    response = await client.post("/tasks", json={...}, headers=auth_headers)
    
    # 插入断点
    import pdb; pdb.set_trace()
    
    assert response.status_code == 200
```

## 测试数据工厂（推荐）

为了简化测试，建议使用工厂模式创建测试数据：

```python
# tests/factories.py
class TaskFactory:
    def __init__(self, client, auth_headers):
        self.client = client
        self.auth_headers = auth_headers
    
    async def create_project(self, name="Test Project"):
        resp = await self.client.post(
            "/projects",
            json={"name": name},
            headers=self.auth_headers
        )
        return resp.json()
    
    async def create_task(self, project_id, title="Test Task", **kwargs):
        data = {
            "project_id": project_id,
            "title": title,
            "task_type": "research",
            **kwargs
        }
        resp = await self.client.post(
            "/tasks",
            json=data,
            headers=self.auth_headers
        )
        return resp.json()
    
    async def claim_and_start(self, task_id, agent_name="test-agent"):
        await self.client.post(
            f"/tasks/{task_id}/claim",
            params={"agent_name": agent_name},
            headers=self.auth_headers
        )
        await self.client.post(
            f"/tasks/{task_id}/start",
            params={"agent_name": agent_name},
            headers=self.auth_headers
        )
```

使用工厂：

```python
async def test_something(self, client, auth_headers):
    factory = TaskFactory(client, auth_headers)
    
    project = await factory.create_project()
    task = await factory.create_task(project["id"])
    await factory.claim_and_start(task["id"])
    
    # 继续测试...
```
