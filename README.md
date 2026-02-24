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

### 2. 启动任务服务

```bash
cd task-service
docker-compose up -d
```

### 3. 创建 Agent

```bash
agent create my-agent
```

### 4. 配置 Agent

编辑 `agents/<agent-name>/.env`：

```env
DISCORD_BOT_TOKEN=你的BotToken
API_KEY=你的APIKey
AGENT_NAME=my-agent

# Task Service 地址
# 本机开发: http://host.docker.internal:8080
# 局域网其他设备: http://<本机IP>:8080
# 云服务器: http://<服务器IP或域名>:8080
TASK_SERVICE_URL=http://host.docker.internal:8080
```

#### 跨网络访问配置

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
│   └── DEPLOYMENT.md        # 部署指南
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

### 项目 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/projects` | POST | 创建项目 |
| `/projects` | GET | 列出项目 |
| `/projects/{id}` | GET | 项目详情 |
| `/projects/{id}/progress` | GET | 项目进度统计 |
| `/projects/{id}/breakdown` | POST | 拆分项目为任务 |

### 任务 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/tasks` | POST | 创建任务 |
| `/tasks` | GET | 列出任务（支持过滤） |
| `/tasks/available` | GET | 可认领的任务（依赖已完成） |
| `/tasks/available-for/{agent}` | GET | 适合某 Agent 的任务（技能匹配） |
| `/tasks/{id}` | GET | 任务详情 |
| `/tasks/{id}/claim` | POST | 认领任务 |
| `/tasks/{id}/start` | POST | 开始执行 |
| `/tasks/{id}/submit` | POST | 提交验收 |
| `/tasks/{id}/release` | POST | 释放任务 |
| `/tasks/{id}/retry` | POST | 重试失败任务 |
| `/tasks/{id}/review` | POST | 验收任务 |

### Agent API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/agents/register` | POST | 注册 Agent |
| `/agents` | GET | 列出 Agent（支持技能过滤） |
| `/agents/{name}` | GET | Agent 详情 |
| `/agents/{name}/heartbeat` | POST | 心跳上报 |
| `/dashboard/stats` | GET | 仪表盘统计 |

### 示例调用

```bash
# 创建项目
curl -X POST http://localhost:8080/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "AI 助手调研", "description": "调研主流 AI 助手"}'

# 拆分任务
curl -X POST http://localhost:8080/projects/1/breakdown \
  -H "Content-Type: application/json" \
  -d '[
    {"title": "需求分析", "task_type": "analysis", "priority": 10, "task_tags": ["planning"]},
    {"title": "竞品调研", "task_type": "research", "priority": 9, "task_tags": ["research"], "dependencies": [0]}
  ]'

# 认领任务
curl -X POST "http://localhost:8080/tasks/1/claim?agent_name=researcher"

# 提交验收
curl -X POST "http://localhost:8080/tasks/1/submit" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "researcher", "result": {"output": "调研报告内容"}}'

# 验收通过
curl -X POST "http://localhost:8080/tasks/1/review?reviewer=coordinator" \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "feedback": "质量很好"}'
```

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
| `AGENT_NAME` | Agent 名称 | agent |
| `TASK_SERVICE_URL` | 任务服务地址 | http://host.docker.internal:8080 |

## 配置说明

### config.example.toml

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
```

## Agent 最佳实践

### 赋予工具
- 安装各种 Skills 到 `workspace/skills/` 目录
- 让 Agent 能根据任务选择合适的工具

### 避免过度分工
- ❌ "你是 Researcher，只能做研究"
- ✅ "你擅长研究，但也能做文案、视频等"

### 使用任务系统

Worker Agent 使用任务系统的完整流程：

#### 1. 注册 Agent 并启动心跳

Agent 启动时必须向 Task Service 注册并启动心跳：

```python
from skills.agent_manager import register_to_channel, start_heartbeat_loop, update_current_task

# 1. 注册到 Task Service
register_to_channel(channel_id="123456", channel_name="#ai项目")

# 2. 启动心跳循环（每 30 秒发送一次）
start_heartbeat_loop(interval_seconds=30)
```

**注意**：心跳是必须的！如果 5 分钟没有心跳，Agent 会被标记为 offline。

#### 2. 多任务模式工作流程

Agent 可以认领多个任务，但同一时间只能执行一个：

```python
def multi_task_workflow():
    """多任务模式工作流示例"""
    
    # 1. 认领多个任务（最多 MAX_CONCURRENT_TASKS 个）
    task_a = claim_task(task_id=1)  # assigned
    task_b = claim_task(task_id=2)  # assigned
    task_c = claim_task(task_id=3)  # assigned
    
    # 2. 开始执行第一个任务
    start_task(task_id=1)           # A: running, B/C: assigned
    update_current_task(task_id=1)  # 更新心跳中的任务ID
    execute_task(task_a)
    submit_task(task_id=1)          # A: reviewing, B/C: assigned
    update_current_task(task_id=None)
    
    # 3. 开始执行第二个任务
    start_task(task_id=2)           # A: reviewing, B: running, C: assigned
    update_current_task(task_id=2)
    execute_task(task_b)
    submit_task(task_id=2)          # A/B: reviewing, C: assigned
    update_current_task(task_id=None)
    
    # 4. 继续执行第三个任务...
```

#### 3. 查找并认领任务

Worker 主动拉取适合自己的任务：

```python
def find_and_claim_task():
    """查找并认领任务"""
    # 获取适合当前 Agent 的任务（技能匹配 + 依赖检查）
    resp = requests.get(
        f"{TASK_SERVICE_URL}/tasks/available-for/{AGENT_NAME}"
    )
    tasks = resp.json()
    
    if not tasks:
        return None
    
    # 认领优先级最高的任务
    task = tasks[0]  # API 已按优先级排序
    task_id = task["id"]
    
    # 认领任务（乐观锁，可能失败）
    resp = requests.post(
        f"{TASK_SERVICE_URL}/tasks/{task_id}/claim",
        params={"agent_name": AGENT_NAME}
    )
    
    if resp.status_code == 200:
        print(f"✅ 认领任务 #{task_id}: {task['title']}")
        return resp.json()
    elif resp.status_code == 429:
        print(f"⏳ 已达最大并发任务数限制")
        return None
    else:
        print(f"❌ 认领失败: {resp.text}")
        return None
```

#### 4. 执行任务

认领后开始执行并定期更新进度：

```python
def start_task(task_id):
    """开始执行任务"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/tasks/{task_id}/start",
        params={"agent_name": AGENT_NAME}
    )
    return resp.json()

def execute_task(task):
    """实际执行任务"""
    task_id = task["id"]
    
    # 1. 开始任务
    start_task(task_id)
    
    # 2. 执行任务内容...
    result = do_actual_work(task)
    
    return result

def do_actual_work(task):
    """实际的工作逻辑（由 Agent 自己实现）"""
    # 这里是 Agent 的核心能力
    # 例如：调研、写作、编程等
    pass
```

#### 5. 提交验收

完成后提交给 Reviewer 验收：

```python
def submit_task(task_id, result):
    """提交任务完成"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/tasks/{task_id}/submit",
        params={"agent_name": AGENT_NAME},
        json={"result": result}  # 任务结果
    )
    
    if resp.status_code == 200:
        print(f"✅ 任务 #{task_id} 已提交验收")
        return resp.json()
    else:
        print(f"❌ 提交失败: {resp.text}")
        return None
```

#### 6. 完整的 Worker 主循环

```python
import time
import threading

def worker_main_loop():
    """Worker Agent 主循环"""
    # 1. 注册
    register_agent()
    
    # 2. 启动心跳
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    
    current_task = None
    
    while True:
        # 如果没有任务，尝试获取
        if not current_task:
            current_task = find_and_claim_task()
            
            if current_task:
                try:
                    # 执行任务
                    result = execute_task(current_task)
                    
                    # 提交验收
                    submit_task(current_task["id"], result)
                    
                    current_task = None
                except Exception as e:
                    print(f"❌ 任务执行失败: {e}")
                    # 释放任务回队列
                    requests.post(
                        f"{TASK_SERVICE_URL}/tasks/{current_task['id']}/release",
                        params={"agent_name": AGENT_NAME}
                    )
                    current_task = None
            else:
                print("⏳ 没有可用任务，等待 10 秒...")
                time.sleep(10)
        else:
            # 正在执行任务，等待完成
            time.sleep(5)

# 启动 Worker
if __name__ == "__main__":
    worker_main_loop()
```

#### 7. 处理验收结果

Agent 可以通过查询任务状态了解验收结果：

```python
def check_task_status(task_id):
    """检查任务状态"""
    resp = requests.get(f"{TASK_SERVICE_URL}/tasks/{task_id}")
    task = resp.json()["task"]
    
    if task["status"] == "completed":
        print(f"🎉 任务 #{task_id} 已通过验收！")
    elif task["status"] == "rejected":
        print(f"❌ 任务 #{task_id} 被拒绝")
        print(f"反馈: {task.get('feedback', '无反馈')}")
        # 可能需要重新认领并修改
    
    return task["status"]
```

#### 使用 Skill 简化

实际使用中，Agent 可以通过 `task-manager` skill 简化操作：

```python
# 在 SOUL.md 中配置 Skill
# Agent 会自动使用 skill 中的工具函数

# 例如用户说："查看我的任务"
# Agent 会调用 get_my_tasks(AGENT_NAME)

# 用户说："认领任务 5"
# Agent 会调用 claim_task(5, AGENT_NAME)
```

## 数据库 Schema

详见 `task-service/schema.sql`，主要表：

- **projects** - 项目信息
- **tasks** - 任务（含优先级、依赖、标签等）
- **agents** - Agent 注册信息（含技能、统计）
- **task_logs** - 任务操作日志

## 常见问题

### Q: 私聊不回复？
A: 设置 `mention_only = false`

### Q: 需要 pairing？
A: 首次启动需要配对，之后不需要

### Q: 任务服务连接失败？
A: 确保 `TASK_SERVICE_URL` 正确，Docker 环境使用 `http://host.docker.internal:8080`

### Q: Agent 如何发现任务？
A: Agent 使用 `task-manager` skill 轮询 `/tasks/available-for/{agent_name}`

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

## License

MIT
