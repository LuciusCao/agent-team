---
name: agent-register
description: Agent 注册到 Discord 频道 - 当用户在频道中 @Agent 时自动注册
metadata:
  {
    openclaw: { emoji: "📝", triggers: ["注册", "register"] },
    zeroclaw: { compatible: true },
  }
---

# Agent Register Skill

当用户在 Discord 频道中 @Agent 时，自动注册到任务系统。

## 触发条件

用户在频道中 @Agent 并说"注册"或"登记"

例如：
- `@researcher 注册`
- `@copy-writer 登记`

## 配置

在 Agent 的环境变量或 config 中配置：

```env
TASK_SERVICE_URL=http://host.docker.internal:8080
AGENT_NAME=researcher
AGENT_ROLE=research
```

## 实现

### 工具函数

```python
import os
import requests

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")

def register_agent_to_channel(agent_name: str, channel_id: str, channel_name: str = None):
    """注册 Agent 到频道"""
    
    # 1. 注册/更新 Agent
    resp = requests.post(
        f"{TASK_SERVICE_URL}/agents/register",
        json={
            "name": agent_name,
            "role": os.getenv("AGENT_ROLE", "unknown"),
            "discord_user_id": os.getenv("DISCORD_BOT_ID", "")
        }
    )
    
    # 2. 记录频道活跃
    requests.post(
        f"{TASK_SERVICE_URL}/agent-channels",
        json={
            "agent_name": agent_name,
            "channel_id": channel_id
        }
    )
    
    return {
        "success": True,
        "message": f"✅ {agent_name} 已注册到 {channel_name or channel_id}"
    }

def get_channel_agents(channel_id: str):
    """查询频道的活跃 Agent"""
    resp = requests.get(f"{TASK_SERVICE_URL}/channels/{channel_id}/agents")
    return resp.json()
```

### 处理流程

```
1. 解析消息: @agent_name 注册
2. 获取 channel_id (从 Discord 消息上下文)
3. 调用 register_agent_to_channel(agent_name, channel_id, channel_name)
4. 回复用户确认
```

### Discord 响应模板

成功：
```
✅ researcher 已注册到 #ai项目
   - 角色: research
   - 状态: online
```

已存在：
```
ℹ️ researcher 已在 #ai项目 注册过
   - 角色: research
   - 最后活跃: 2分钟前
```

错误：
```
❌ 注册失败: {error_message}
```

## 使用示例

```
用户: @researcher 注册
Agent: ✅ researcher 已注册到 #ai项目
       - 角色: research
       - 状态: online
```
