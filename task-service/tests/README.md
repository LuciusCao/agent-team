# Task Service 测试

## 运行测试

### 安装依赖

```bash
cd task-service
pip install pytest pytest-asyncio httpx
```

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行特定测试

```bash
# 只测试项目 API
pytest tests/test_app.py::TestProjects -v

# 只测试任务 API
pytest tests/test_app.py::TestTasks -v

# 只测试认证
pytest tests/test_app.py::TestAuth -v
```

### 带覆盖率报告

```bash
pip install pytest-cov
pytest tests/ --cov=app --cov-report=html
```

## 测试环境

测试使用独立的数据库 `taskmanager_test`，会自动：
1. 创建测试数据库
2. 执行 schema.sql 初始化
3. 运行测试
4. 测试结束后保留数据（方便调试）

## 测试分类

| 测试类 | 描述 |
|--------|------|
| `TestHealth` | 健康检查 |
| `TestProjects` | 项目 CRUD |
| `TestTasks` | 任务 CRUD、认领、状态流转 |
| `TestAgents` | Agent 注册、心跳 |
| `TestAuth` | API 认证 |
| `TestRateLimit` | 速率限制 |
| `TestTimeouts` | 超时配置 |

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
