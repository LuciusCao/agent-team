# Agent Team

使用 ZeroClaw 部署的多 Agent 团队协作系统。

> **核心理念**：Agent 是全能型工作者，任务由 Agent 主动认领，而非中央分发。

## 快速开始

### 1. 安装依赖

- Docker Desktop

将项目路径加入到.zshrc
```bash
export PATH="$PATH:$HOME/GitHub/agent-team"
source ~/.zshrc
```

### 2. 创建 Agent

```bash
agent create my-agent
```

### 3. 配置 Agent

编辑 `agents/<agent-name>/.env`：

```env
DISCORD_BOT_TOKEN=你的BotToken
API_KEY=你的APIKey
```

### 4. 生成配置并启动

```bash
agent config my-agent
agent start my-agent
```

## 项目结构

```
agent-team/
├── agent                    # 统一入口脚本
├── scripts/               # 管理脚本
│   ├── config.sh
│   ├── create.sh
│   ├── start.sh
│   └── stop.sh
├── templates/             # 模板文件
│   ├── .env.example
│   ├── config.example.toml
│   ├── docker-compose.example.yml
│   ├── SOUL.example.md
│   └── AGENTS.example.md
├── agents/               # Agent 目录
│   ├── researcher/
│   ├── copy-writer/
│   └── video-master/
├── task-service/         # 任务服务
│   ├── app.py             # FastAPI 服务
│   ├── schema.sql         # 数据库 Schema
│   ├── skill/             # Agent CLI 工具
│   └── docker-compose.yml
└── shared/               # 共享文件夹
```

## 任务认领模式

### 核心理念

- **Agent 是全能型**：每个 Agent 都能处理各种任务
- **任务公开**：所有任务对所有 Agent 可见
- **主动认领**：Agent 根据自身能力和当前负载主动认领任务
- **自然协作**：Agent 之间通过协作完成复杂任务，而非固定分工

### 优势

1. **更高的自主性**：Agent 自主决策，而非被动执行
2. **负载均衡**：Agent 根据空闲状态自动平衡任务
3. **扩展性强**：新增 Agent 无需修改调度逻辑
4. **更接近真实协作**：像人类团队一样自然协作

### Task Service

任务服务为 Agent 提供任务池功能：

#### 启动任务服务

```bash
cd task-service
docker-compose up -d
```

#### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/tasks/available` | GET | 获取可认领的任务 |
| `/tasks/{id}/claim?agent_name=xxx` | POST | Agent 认领任务 |
| `/tasks/{id}/release?agent_name=xxx` | POST | 释放任务回池 |
| `/tasks` | GET | 列出任务 |
| `/tasks/{id}` | PATCH | 更新任务状态 |

#### Agent CLI 工具

在 Agent 容器中可以使用 `task` 命令：

```bash
# 查看可认领任务
task available

# 认领任务
task claim 123

# 查看我的任务
task mine

# 更新任务状态
task update 123 completed '{"output": "完成内容"}'
```

#### 任务流程

```
pending（待认领）
    ↓
running（进行中）
    ↓
approval（审核中）
    ↓
completed（已完成）
```

## 使用方法

| 命令 | 说明 |
|------|------|
| `agent create <name>` | 创建新 Agent |
| `agent config <name>` | 生成配置 |
| `agent start [name]` | 启动 (无参数启动所有) |
| `agent stop [name]` | 停止 (无参数停止所有) |

## 环境变量

在每个 agent 的 `.env` 中配置：

| 变量 | 说明 | 默认值 |
|------|------|---------|
| `PROJECT_ROOT` | 项目根目录 | ~/GitHub/agent-team |
| `PORT` | 端口 | 43001 |
| `DISCORD_BOT_TOKEN` | Discord Bot | - |
| `API_KEY` | LLM API Key | - |
| `PROVIDER` | LLM Provider | kimi-code |
| `MODEL` | 模型 | kimi-k2.5 |

## 配置说明

### config.example.toml

- `mention_only = true` → 大厅需要 @ 才回复
- `compact_context = true` → 压缩上下文
- `browser.enabled = true` → 启用浏览器
- `heartbeat.enabled = true` → 启用心跳

## Agent 最佳实践

### 赋予工具
- 安装各种 Skills 到 `workspace/skills/` 目录
- 让 Agent 能根据任务选择合适的工具

### 避免过度分工
- ❌ "你是 Researcher，只能做研究"
- ✅ "你擅长研究，但也能做文案、视频等"

## 常见问题

### Q: 私聊不回复？
A: 设置 `mention_only = false`

### Q: 需要 pairing？
A: 首次启动需要配对，之后不需要
