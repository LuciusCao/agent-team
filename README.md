# Agent Team

使用 ZeroClaw 部署的多 Agent 团队协作系统。

## 快速开始

### 1. 安装依赖

- Docker Desktop

将项目路径加入到.zshrc
```bash
export PATH="$PATH:$HOME/GitHub/agent-team"
source ~/.zshrc
````

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
└── shared/               # 共享文件夹
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

## 常见问题

### Q: 私聊不回复？
A: 设置 `mention_only = false`

### Q: 需要 pairing？
A: 首次启动需要配对，之后不需要

---

## 任务管理系统

### 架构

```
┌─────────────────────────────────────────────┐
│         本地 API 服务 (FastAPI)               │
│  PostgreSQL 存储任务数据                       │
│  - POST /tasks        创建任务                │
│  - GET /tasks         列表查询                │
│  - PATCH /tasks/:id  更新状态                │
│  - POST /tasks/:id/review  验收              │
└─────────────────────────────────────────────┘
                    ↑
                    │ Agent 调用 API
                    ↓
┌─────────────────────────────────────────────┐
│         Discord 频道                          │
│  Agent 根据任务状态自行发送消息                  │
└─────────────────────────────────────────────┘
```

### 数据模型

#### 项目 (projects)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| name | VARCHAR | 项目名 |
| discord_channel_id | VARCHAR | Discord 频道ID |
| description | TEXT | 描述 |

#### 任务 (tasks)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| project_id | INT | 所属项目 |
| title | VARCHAR | 任务标题 |
| task_type | VARCHAR | research/copywrite/video/review/publish |
| status | VARCHAR | pending/running/approval/completed/failed |
| assignee_agent | VARCHAR | 负责的 Agent |
| reviewer_id | VARCHAR | 验收人 Discord ID |
| reviewer_mention | VARCHAR | 验收人 @mention |
| acceptance_criteria | TEXT | 验收标准 |
| parent_task_id | INT | 父任务ID (任务拆分) |
| dependencies | INT[] | 依赖的任务ID |
| result | JSONB | 任务产出结果 |
| feedback | TEXT | 验收反馈/修改意见 |
| created_by | VARCHAR | 创建者 |
| due_at | TIMESTAMP | 截止时间 |

### 工作流

1. **创建项目**: 指定项目名和 Discord channel
2. **拆分子任务**: 每个任务指定 assignee、reviewer、acceptance_criteria
3. **任务派发**: 
   - 写入 PostgreSQL
   - Agent 调用 GET /tasks 获取任务
4. **执行**: 
   - Agent 更新状态为 "running"
   - 执行任务
   - 更新状态为 "approval"
   - **自行发送 Discord 消息 @验收人 申请验收**
5. **验收**:
   - 验收人检查结果是否符合 acceptance_criteria
   - 通过: status = "completed" → 触发下游任务
   - 拒绝: status = "running" + 写入 feedback → **Agent 发送 Discord @负责人 反馈**
6. **修改**: Agent 根据 feedback 修改后重新提交验收

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects | 创建项目 |
| GET | /projects | 项目列表 |
| GET | /projects/{id} | 项目详情 |
| POST | /tasks | 创建任务 |
| GET | /tasks | 任务列表 |
| GET | /tasks/{id} | 任务详情 |
| PATCH | /tasks/{id} | 更新任务 |
| POST | /tasks/{id}/review | 验收任务 |

### Discord 消息模板

#### 新任务派发
```markdown
## 📋 新任务创建
**项目**: {project_name}
**任务**: {task_title}
**类型**: {task_type}
**负责人**: @{assignee}
**验收人**: {reviewer_mention}
**验收标准**:
{acceptance_criteria}
**截止时间**: {due_at}
```

#### 申请验收
```markdown
## ✅ 任务完成 - 申请验收
**任务**: {task_title}
**负责人**: {assignee}
**结果**: {result_summary}
**请 {reviewer_mention} 验收**
```

#### 验收通过
```markdown
## 🎉 验收通过
**任务**: {task_title}
**验收人**: {reviewer}
**状态**: completed
```

#### 验收拒绝
```markdown
## ❌ 验收不通过 - 需修改
**任务**: {task_title}
**验收人**: {reviewer}
**反馈**:
{feedback}

**请 {assignee} 根据反馈修改后重新提交验收**
```

### 启动服务

```bash
cd task-service
docker-compose up -d

# 等待数据库就绪
docker exec -it taskmanager-db psql -U taskmanager -d taskmanager -f /docker-entrypoint-initdb.d/schema.sql

# 测试
curl http://localhost:8080/
```

### Agent 注册与心跳

#### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /agents/register | 注册 Agent |
| POST | /agents/{name}/heartbeat | Agent 心跳 |
| GET | /agents | 列出 Agent |
| GET | /agents/{name} | Agent 详情 |
| DELETE | /agents/{name} | 注销 Agent |

#### 注册 Agent

```bash
curl -X POST http://localhost:8080/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "researcher",
    "discord_user_id": "123456789",
    "role": "research",
    "capabilities": {"web_search": true, "browser": true}
  }'
```

#### 心跳

Agent 需要每分钟发送心跳：

```bash
curl -X POST http://localhost:8080/agents/researcher/heartbeat
```

超过 5 分钟没有心跳的 Agent 会被自动设为 offline。

---

### Agent 频道注册机制

#### 设计目标

当用户在 Discord 频道中 @Agent 时，Agent 自动注册到该频道，表示"我可以响应这个频道的任务"。

#### 数据库设计

```sql
-- Agent 活跃频道表
CREATE TABLE IF NOT EXISTS agent_channels (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    last_seen TIMESTAMP DEFAULT NOW(),
    UNIQUE(agent_name, channel_id)
);
```

#### 注册流程

```
1. 用户在频道中 @researcher
2. Agent 收到消息，调用 skill
3. Skill 调用 Task Service API:
   - POST /agents/register (首次注册/更新)
   - POST /agent_channels (记录频道活跃)
4. 返回注册结果
```

#### API 端点（新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /agents/register | 注册 Agent（带 channel_id） |
| POST | /agent-channels | 记录 Agent 活跃频道 |
| GET | /agents/{name}/channels | 查询 Agent 活跃的所有频道 |
| DELETE | /agent-channels | 移除 Agent 在某频道的活跃状态 |

#### Skill 设计

**Skill 1: agent-register（注册）**
- 触发：用户在频道中 @Agent
- 行为：
  1. 解析 agent name 和 channel id
  2. 调用 /agents/register
  3. 调用 /agent-channels 创建记录
  4. 回复用户确认

**Skill 2: agent-unregister（移除）**
- 触发：用户说"移除 @agent" 或 "取消 @agent 的资格"
- 行为：
  1. 解析 agent name 和 channel id
  2. 调用 DELETE /agent-channels
  3. 回复用户确认

#### 使用示例

```
# 用户在 #ai项目 频道说:
@researcher 注册

# Agent 回复:
✅ researcher 已注册到 #ai项目
   - 角色: research
   - 能力: web_search, browser

# 用户说:
移除 @researcher

# Agent 回复:
✅ researcher 已从 #ai项目 移除
```

#### 查询可用 Agent

```bash
# 查询某频道有哪些可用 Agent
GET /agents?channel_id=123456

# 查询 Agent 在哪些频道活跃
GET /agents/researcher/channels
```
