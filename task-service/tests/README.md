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
| `TestConcurrency` | 并发和竞态条件 | 中 |
| `TestIdempotency` | 幂等性保证 | 高 |
| `TestAgents` | Agent 注册、心跳 | 中 |
| `TestAuth` | API 认证 | 高 |
| `TestRateLimit` | 速率限制 | 中 |
| `TestTimeouts` | 超时配置 | 中 |

## 测试覆盖范围

### 任务生命周期测试 (TestTaskLifecycle)

覆盖完整的任务状态流转：
- `test_full_task_lifecycle_success`: pending → assigned → running → reviewing → completed
- `test_task_lifecycle_rejected`: pending → assigned → running → reviewing → rejected → pending
- `test_cannot_start_without_claim`: 验证未认领不能开始
- `test_cannot_submit_without_start`: 验证未开始不能提交
- `test_release_task`: 验证任务释放

### 任务依赖测试 (TestTaskDependencies)

- `test_cannot_claim_with_unfinished_deps`: 依赖未完成时不能认领
- `test_circular_dependencies_detection`: 循环依赖检测

### 并发测试 (TestConcurrency)

- `test_claim_race_condition`: 验证认领竞态条件（只有一个 Agent 能成功）

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
