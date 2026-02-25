# Task Service

Agent Team 的任务管理服务，提供任务分配、Agent 管理、项目跟踪等功能。

## 快速开始

### 使用开发脚本（推荐）

```bash
# 启动开发环境
./scripts/dev.sh start --fresh

# 生成测试数据
./scripts/dev.sh seed

# 查看日志
./scripts/dev.sh logs -f

# 运行测试
./scripts/dev.sh test
```

详细脚本文档：[scripts/README.md](scripts/README.md)

### 手动启动

```bash
# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

**注意**: 推荐使用 `docker compose`（新版），旧版 `docker-compose` 也兼容。

## 项目结构

```
task-service/
├── main.py              # FastAPI 应用入口
├── config.py            # 集中配置管理
├── database.py          # 数据库连接池
├── security.py          # 认证和限流
├── utils.py             # 工具函数
├── background.py        # 后台任务
├── models.py            # Pydantic 模型
├── schema.sql           # 数据库 Schema
├── routers/             # API 路由
│   ├── tasks.py         # 任务 API
│   ├── agents.py        # Agent API
│   ├── projects.py      # 项目 API
│   ├── channels.py      # 频道 API
│   └── dashboard.py     # 仪表盘 API
├── scripts/             # 开发工具脚本
│   ├── dev.sh           # 主入口
│   ├── dev-start.sh     # 启动
│   ├── dev-clean.sh     # 清理
│   ├── dev-logs.sh      # 日志
│   ├── dev-test.sh      # 测试
│   └── dev-seed.sh      # 生成数据
├── tests/               # 测试套件
├── pyproject.toml       # 项目配置
└── docker-compose.yml   # Docker 编排
```

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

### API 端点

#### 项目 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/projects` | POST | 创建项目 |
| `/v1/projects` | GET | 列出项目 |
| `/v1/projects/{id}` | GET | 项目详情 |
| `/v1/projects/{id}/progress` | GET | 项目进度统计 |
| `/v1/projects/{id}/breakdown` | POST | 拆分项目为任务 |
| `/v1/projects/{id}` | DELETE | 删除项目（软删除） |
| `/v1/projects/{id}/restore` | POST | 恢复软删除的项目 |

#### 任务 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/tasks` | POST | 创建任务 |
| `/v1/tasks` | GET | 列出任务（支持过滤） |
| `/v1/tasks/available` | GET | 可认领的任务（依赖已完成） |
| `/v1/tasks/available-for/{agent}` | GET | 适合某 Agent 的任务（技能匹配） |
| `/v1/tasks/{id}` | GET | 任务详情 |
| `/v1/tasks/{id}/claim` | POST | 认领任务 |
| `/v1/tasks/{id}/start` | POST | 开始执行 |
| `/v1/tasks/{id}/submit` | POST | 提交验收 |
| `/v1/tasks/{id}/release` | POST | 释放任务 |
| `/v1/tasks/{id}/retry` | POST | 重试失败任务 |
| `/v1/tasks/{id}/review` | POST | 验收任务 |
| `/v1/tasks/{id}` | DELETE | 删除任务（软删除） |
| `/v1/tasks/{id}/restore` | POST | 恢复软删除的任务 |

#### Agent API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/agents/register` | POST | 注册 Agent |
| `/v1/agents` | GET | 列出 Agent（支持技能过滤） |
| `/v1/agents/{name}` | GET | Agent 详情 |
| `/v1/agents/{name}/heartbeat` | POST | 心跳上报 |
| `/v1/agents/{name}` | DELETE | 注销 Agent（软删除） |
| `/v1/agents/{name}/restore` | POST | 恢复软删除的 Agent |

#### 仪表盘 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/dashboard/stats` | GET | 仪表盘统计 |

### 示例调用

```bash
# 创建项目
curl -X POST http://localhost:8080/v1/projects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"name": "AI 助手调研", "description": "调研主流 AI 助手"}'

# 拆分任务
curl -X POST http://localhost:8080/v1/projects/1/breakdown \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '[
    {"title": "需求分析", "task_type": "analysis", "priority": 10, "task_tags": ["planning"]},
    {"title": "竞品调研", "task_type": "research", "priority": 9, "task_tags": ["research"]}
  ]'

# 认领任务
curl -X POST "http://localhost:8080/v1/tasks/1/claim?agent_name=researcher" \
  -H "X-API-Key: your-api-key"

# 开始任务
curl -X POST "http://localhost:8080/v1/tasks/1/start?agent_name=researcher" \
  -H "X-API-Key: your-api-key"

# 提交验收
curl -X POST "http://localhost:8080/v1/tasks/1/submit?agent_name=researcher" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"output": "调研报告内容", "summary": "完成了 5 个竞品的调研"}'

# 验收通过
curl -X POST "http://localhost:8080/v1/tasks/1/review?reviewer=coordinator" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"approved": true, "feedback": "质量很好"}'
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | 数据库连接字符串 | postgresql://localhost:5432/taskmanager |
| `DB_POOL_MIN_SIZE` | 连接池最小连接数 | 2 |
| `DB_POOL_MAX_SIZE` | 连接池最大连接数 | 10 |
| `DB_COMMAND_TIMEOUT` | 数据库命令超时（秒） | 60 |
| `DB_MAX_QUERIES` | 单个连接最大查询数 | 100000 |
| `API_KEY` | API 认证密钥 | - |
| `LOG_LEVEL` | 日志级别 | INFO |
| `MAX_CONCURRENT_TASKS_PER_AGENT` | Agent 最大并发任务数 | 3 |
| `DEFAULT_TASK_TIMEOUT_MINUTES` | 默认任务超时时间 | 120 |
| `RATE_LIMIT_MAX_REQUESTS` | 速率限制最大请求数 | 100 |

## 开发指南

### 添加新的 API 端点

1. 在 `routers/` 下找到对应模块或创建新文件
2. 使用 `router = APIRouter()` 创建路由
3. 在 `main.py` 中注册路由

### 数据库变更

1. 修改 `schema.sql`
2. 使用 migration 脚本确保向后兼容
3. 更新相关查询代码

### 运行测试

```bash
# 所有测试
pytest tests/ -v

# 特定测试
pytest tests/ -k test_name

# 覆盖率
pytest tests/ --cov=. --cov-report=html
```

## 核心功能

### 任务生命周期

```
pending（待认领）
    ↓ claim
assigned（已分配）
    ↓ start
running（进行中）
    ↓ submit
reviewing（待验收）
    ↓ review
    ├─▶ completed（已完成）✅
    └─▶ rejected（已拒绝）❌ ──▶ pending（重新认领）
```

### 软删除

所有主要实体（tasks, agents, projects）支持软删除：

- 默认 DELETE 操作是软删除
- 可通过 `?hard=true` 参数物理删除
- 软删除记录可通过 `/restore` 端点恢复
- 30 天后自动清理

### 后台任务

- **heartbeat_monitor**: 检测离线 Agent
- **stuck_task_monitor**: 释放超时任务
- **soft_delete_cleanup_monitor**: 清理过期软删除记录

## 常见问题

### 数据库连接失败

```bash
# 检查 postgres 是否运行
docker compose ps

# 查看 postgres 日志
docker compose logs postgres

# 重置数据库
./scripts/dev-clean.sh --all
```

### 端口被占用

```bash
# 检查端口占用
lsof -i :8080

# 修改 docker-compose.yml 中的端口映射
```

### 测试失败

```bash
# 确保服务在运行
./scripts/dev.sh status

# 重新生成测试数据
./scripts/dev.sh seed --clean

# 详细输出
./scripts/dev.sh test -v
```

## License

MIT
