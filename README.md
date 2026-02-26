# Agent Team

使用 ZeroClaw 部署的多 Agent 团队协作系统。

> **核心理念**：Agent 是全能型工作者，任务由 Agent 主动认领，而非中央分发。

## 新功能：Agent Workforce v1 🚀

完整的分布式任务协作系统，支持：

- ✅ **任务依赖** - 前置任务未完成时无法认领
- ✅ **优先级** - 1-10 级优先级，高优先级优先处理  
- ✅ **技能匹配** - Agent 技能标签与任务标签自动匹配
- ✅ **验收打回** - 支持通过/拒绝，拒绝后自动回队列
- ✅ **项目拆分** - 项目经理自动拆分项目为任务
- ✅ **进度监控** - 实时查看项目完成百分比
- ✅ **重试机制** - 失败任务自动重试，超次数后标记失败
- ✅ **卡住检测** - 运行超2小时任务自动释放
- ✅ **多任务模式** - Agent 可认领多个任务，依次执行（默认最多3个）
- ✅ **心跳机制** - Agent 定期发送心跳，自动检测离线

## 快速开始

### 1. 安装依赖

- Docker Desktop

将项目路径加入到.zshrc
```bash
export PATH="$PATH:$HOME/GitHub/agent-team"
source ~/.zshrc
```
---

### 2. 开发环境快速启动

使用开发工具脚本快速管理环境：

```bash
cd task-service

# 启动开发环境（首次或需要干净环境）
./scripts/dev.sh start --fresh

# 生成测试数据
./scripts/dev.sh seed --projects 3 --tasks 5
```

更多脚本功能详见 [task-service/scripts/README.md](task-service/scripts/README.md)

---

### 3. 创建 Agent

```bash
agent create my-agent
```

### 4. 配置 Agent

编辑 `agents/<agent-name>/.env`：

在每个 agent 的 `.env` 中配置：
```env

| 变量 | 说明 | 默认值 |
|------|------|---------|
| `PROJECT_ROOT` | 项目根目录 | ~/GitHub/agent-team |
| `PORT` | 端口 | 43001 |
| `DISCORD_BOT_TOKEN` | Discord Bot | - |
| `API_KEY` | LLM API Key | - |
| `PROVIDER` | LLM Provider | kimi-code |
| `MODEL` | 模型 | kimi-k2.5 |
| `AGENT_NAME` | Agent 名称 | agent |
| `TASK_SERVICE_URL` | 任务服务地址 | http://host.docker.internal:8080 |
```
#### 配置说明
##### config.example.toml

```toml
[discord]
mention_only = true          # 大厅需要 @ 才回复
compact_context = true       # 压缩上下文

[browser]
enabled = true               # 启用浏览器

[heartbeat]
enabled = true               # 启用心跳

[skills]
paths = ["./skills"]         # Skill 目录
DISCORD_BOT_TOKEN=你的BotToken
API_KEY=你的APIKey
AGENT_NAME=my-agent
```

##### 跨网络访问配置

**场景1: Agent 运行在同一台机器**
```env
TASK_SERVICE_URL=http://host.docker.internal:8080
```

**场景2: Agent 运行在局域网其他设备**
```bash
# 1. 确保 task-service 绑定到 0.0.0.0（已默认配置）
# 2. 在 Agent 设备上配置本机 IP
TASK_SERVICE_URL=http://192.168.1.100:8080  # 运行 task-service 的机器 IP
```

**场景3: Agent 运行在云服务器**
```bash
# 1. 云服务器需要有公网 IP 或域名
# 2. 配置安全组开放 8080 端口
# 3. 建议使用 HTTPS + 认证
TASK_SERVICE_URL=https://task-service.your-domain.com
```

### 5. 生成配置并启动

```bash
agent config my-agent
agent start my-agent
```

## 项目结构

```
agent-team/
├── agent                    # 统一入口脚本
├── scripts/                 # 管理脚本
│   ├── config.sh
│   ├── create.sh
│   ├── start.sh
│   └── stop.sh
├── templates/               # 模板文件
│   ├── .env.example
│   ├── config.example.toml
│   ├── docker-compose.example.yml
│   ├── SOUL.example.md
│   └── AGENTS.example.md
├── agents/                  # Agent 目录
│   ├── researcher/
│   ├── copy-writer/
│   └── video-master/
├── task-service/            # 任务服务 (FastAPI + PostgreSQL)
│   ├── main.py              # 应用入口
│   ├── database.py          # 数据库连接
│   ├── security.py          # 认证和限流
│   ├── models.py            # Pydantic 模型
│   ├── utils.py             # 工具函数
│   ├── background.py        # 后台任务
│   ├── routers/             # API 路由
│   │   ├── __init__.py
│   │   ├── projects.py      # 项目 API
│   │   ├── tasks.py         # 任务 API
│   │   ├── agents.py        # Agent API
│   │   ├── dashboard.py     # 仪表盘 API
│   │   └── channels.py      # 频道 API
│   ├── schema.sql           # 数据库 Schema
│   ├── docker-compose.yml
│   ├── DEPLOYMENT.md        # 部署指南
│   ├── CHANGELOG.md         # 版本变更记录
│   └── tests/               # 测试套件
├── skills/                  # Agent Skills
│   ├── agent-manager/       # Agent 管理（注册/移除/查询）
│   ├── project-manager/     # 项目管理（创建/拆分/监控）
│   └── task-manager/        # 任务管理（CRUD/验收/CLI）
└── shared/                  # 共享文件夹
```

## 任务协作模式

### 核心理念

- **Agent 主动认领**：不是被动分配，Worker 主动拉取适合的任务
- **多任务模式**：一个 Agent 可以同时处理多个任务（默认最多 3 个，可配置）
- **任务公开**：所有任务对所有 Agent 可见
- **依赖检查**：前置任务未完成时不能认领
- **验收机制**：Reviewer 验收，不合格打回重做

### 多任务模式配置

通过环境变量配置每个 Agent 的最大并发任务数：

```bash
# docker-compose.yml
services:
  task-service:
    environment:
      MAX_CONCURRENT_TASKS_PER_AGENT: 3  # 默认 3 个，设为 1 则单任务模式
```

当 Agent 达到最大并发数时，将无法认领新任务，直到完成或释放现有任务。

### 任务执行限制

- **认领**：可以认领多个任务（`assigned` 状态）
- **执行**：同一时间只能执行一个任务（`running` 状态）
- **验收**：可以提交多个任务等待验收（`reviewing` 状态）

这意味着 Agent 可以：
1. 认领任务 A、B、C（都是 assigned）
2. 开始执行任务 A（A 变为 running，B、C 保持 assigned）
3. 完成 A 后提交验收（A 变为 reviewing）
4. 开始执行任务 B（B 变为 running）
5. 以此类推...

### 任务状态流转

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

### 角色分工

| 角色 | 职责 | 典型 Agent |
|------|------|-----------|
| **Project Manager** | 创建项目、拆分任务、监控进度 | project-manager |
| **Worker** | 主动认领任务、执行、提交 | researcher, copy-writer, developer |
| **Reviewer** | 验收交付物、决定通过/打回 | reviewer, coordinator |

## Task Service API

Task Service 提供完整的 REST API 用于任务管理。详细 API 文档请参见 [task-service/README.md](task-service/README.md)。

### 快速参考

| 功能 | 端点 |
|------|------|
| 项目管理 | `/v1/projects` |
| 任务管理 | `/v1/tasks` |
| Agent 管理 | `/v1/agents` |
| 仪表盘 | `/v1/dashboard/stats` |

API 文档（Swagger UI）：http://localhost:8080/docs

## Skills

### task-manager
管理任务的 Skill，Agent 可以用它：
- 查看可认领任务
- 认领/释放任务
- 更新任务状态
- 验收任务

### project-manager (新)
项目经理专用 Skill：
- 创建项目
- 自动拆分任务
- 监控项目进度
- 生成进度报告

### agent-manager
Agent 生命周期管理：
- 注册到频道
- 从频道移除
- 查询频道活跃 Agent

---

## Agent 最佳实践

### 赋予工具
- 安装各种 Skills 到 `workspace/skills/` 目录
- 让 Agent 能根据任务选择合适的工具

### 避免过度分工
- ❌ "你是 Researcher，只能做研究"
- ✅ "你擅长研究，但也能做文案、视频等"

### 使用任务系统

Worker Agent 可以通过 `task-manager` skill 简化操作：

```python
# 在 SOUL.md 中配置 Skill
# Agent 会自动使用 skill 中的工具函数

# 例如用户说："查看我的任务"
# Agent 会调用 get_my_tasks(AGENT_NAME)

# 用户说："认领任务 5"
# Agent 会调用 claim_task(5, AGENT_NAME)
```

## 开发工具

### 开发脚本（推荐）

项目提供了便捷的开发脚本，位于 `task-service/scripts/` 目录：

```bash
cd task-service

# 查看所有可用命令
./scripts/dev.sh help

# 常用命令
./scripts/dev.sh start --fresh    # 干净启动环境
./scripts/dev.sh seed             # 生成测试数据
./scripts/dev.sh logs -f          # 跟踪日志
./scripts/dev.sh test             # 运行测试
./scripts/dev.sh clean --all      # 完全清空环境
```

详细文档：[task-service/scripts/README.md](task-service/scripts/README.md)

### API 版本

当前支持 API v1，所有端点以 `/v1/` 开头。旧的无版本前缀端点仍然可用但已标记为 deprecated。

```
# 推荐
GET /v1/tasks
POST /v1/projects

# 已废弃（仍可用）
GET /tasks
POST /projects
```

### 软删除

任务、Agent 和项目支持软删除：

```bash
# 软删除（默认）
DELETE /v1/tasks/1

# 物理删除
DELETE /v1/tasks/1?hard=true

# 恢复软删除
POST /v1/tasks/1/restore
```

软删除的记录会在 30 天后自动清理。

## 数据库 Schema

详见 `task-service/schema.sql`，主要表：

- **projects** - 项目信息
- **tasks** - 任务（含优先级、依赖、标签等）
- **agents** - Agent 注册信息（含技能、统计）
- **task_logs** - 任务操作日志

---

## Roadmap

- [x] 任务依赖检查
- [x] 优先级系统
- [x] 技能匹配
- [x] 验收打回机制
- [x] 项目拆分
- [x] 进度监控
- [ ] Web Dashboard 可视化
- [ ] 更多项目模板
- [ ] Agent 绩效分析
- [ ] 动态优先级调整

## 相关文档

- [Task Service 详细文档](task-service/README.md)
- [开发工具脚本](task-service/scripts/README.md)
- [测试文档](task-service/tests/README.md)
- [部署指南](task-service/DEPLOYMENT.md)
- [版本变更记录](task-service/CHANGELOG.md)

## License

MIT
