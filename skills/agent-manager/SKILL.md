---
name: agent-manager
description: Agent 管理 - 注册到频道、从频道移除、查询频道 Agent
metadata:
  {
    openclaw: { emoji: "📍", triggers: ["注册", "移除", "注销", "频道成员", "有哪些 Agent"] },
    zeroclaw: { compatible: true },
  }
---

# Agent Manager Skill

管理 Agent 在 Discord 频道的生命周期：
- 注册 Agent 到频道
- 从频道移除 Agent
- 查询频道中的活跃 Agent

## 触发条件

### 注册
- `@agent 注册`
- `@agent 登记`
- `注册 @agent`

### 移除
- `移除 @agent`
- `@agent 移除`
- `取消 @agent 资格`

### 查询
- `这个频道有哪些 Agent？`
- `列出活跃 Agent`

## 配置

```env
TASK_SERVICE_URL=http://host.docker.internal:8080
AGENT_NAME=researcher
AGENT_ROLE=research
```

## 工具函数

```python
import os
import requests

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")
AGENT_NAME = os.getenv("AGENT_NAME", "agent")
AGENT_ROLE = os.getenv("AGENT_ROLE", "unknown")

def register_to_channel(channel_id: str, channel_name: str = None):
    """注册当前 Agent 到频道"""
    # 1. 注册/更新 Agent
    resp = requests.post(
        f"{TASK_SERVICE_URL}/agents/register",
        json={
            "name": AGENT_NAME,
            "role": AGENT_ROLE,
            "discord_user_id": os.getenv("DISCORD_BOT_ID", "")
        }
    )
    
    # 2. 记录频道活跃
    requests.post(
        f"{TASK_SERVICE_URL}/agent-channels",
        json={"agent_name": AGENT_NAME, "channel_id": channel_id}
    )
    
    return {"success": True, "message": f"✅ {AGENT_NAME} 已注册到 {channel_name or channel_id}"}

def unregister_from_channel(channel_id: str, channel_name: str = None):
    """从频道移除当前 Agent"""
    resp = requests.delete(
        f"{TASK_SERVICE_URL}/agent-channels",
        json={"agent_name": AGENT_NAME, "channel_id": channel_id}
    )
    
    if resp.status_code == 200:
        return {"success": True, "message": f"✅ {AGENT_NAME} 已从 {channel_name or channel_id} 移除"}
    else:
        return {"success": False, "message": f"❌ 移除失败"}

def get_channel_agents(channel_id: str):
    """获取频道的活跃 Agent"""
    resp = requests.get(f"{TASK_SERVICE_URL}/channels/{channel_id}/agents")
    return resp.json()

def get_my_channels():
    """获取当前 Agent 活跃的所有频道"""
    resp = requests.get(f"{TASK_SERVICE_URL}/agents/{AGENT_NAME}/channels")
    return resp.json()
```

## 使用示例

### 注册
```
用户: @researcher 注册
Agent: ✅ researcher 已注册到 #ai项目
       - 角色: research
       - 状态: online
```

### 移除
```
用户: 移除 @researcher
Agent: ✅ researcher 已从 #ai项目 移除
```

### 查询频道 Agent
```
用户: 这个频道有哪些 Agent？
Agent: 当前频道活跃的 Agent：
       - @researcher (research)
       - @copy-writer (copywrite)
       - @video-master (video)
```
