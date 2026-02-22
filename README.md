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
