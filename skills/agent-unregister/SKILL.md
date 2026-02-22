---
name: agent-unregister
description: 从 Discord 频道移除 Agent - 当用户说"移除 @agent"时触发
metadata:
  {
    openclaw: { emoji: "🗑️", triggers: ["移除", "unregister", "删除", "取消资格"] },
    zeroclaw: { compatible: true },
  }
---

# Agent Unregister Skill

当用户说"移除 @agent"时，从频道中移除该 Agent 的活跃状态。

## 触发条件

用户在频道中说：
- `移除 @researcher`
- `@researcher 移除`
- `取消 @copy-writer 的资格`
- `删除 @video-master`

## 实现

### 工具函数

```python
import requests
import os

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")

def unregister_agent_from_channel(agent_name: str, channel_id: str, channel_name: str = None):
    """从频道移除 Agent"""
    
    resp = requests.delete(
        f"{TASK_SERVICE_URL}/agent-channels",
        json={
            "agent_name": agent_name,
            "channel_id": channel_id
        }
    )
    
    if resp.status_code == 200:
        return {
            "success": True,
            "message": f"✅ {agent_name} 已从 {channel_name or channel_id} 移除"
        }
    else:
        return {
            "success": False,
            "message": f"❌ 移除失败: {resp.text}"
        }
```

### 处理流程

```
1. 解析消息: 移除 @agent_name
2. 获取 channel_id
3. 调用 unregister_agent_from_channel(agent_name, channel_id)
4. 回复用户确认
```

### Discord 响应模板

成功：
```
✅ researcher 已从 #ai项目 移除
```

未注册：
```
ℹ️ researcher 不在 #ai项目 中
```

错误：
```
❌ 移除失败: {error_message}
```

## 使用示例

```
用户: 移除 @researcher
Agent: ✅ researcher 已从 #ai项目 移除

用户: 取消 @copy-writer 的资格
Agent: ✅ copy-writer 已从 #ai项目 移除
```

## 注意事项

- 只移除 Agent 在当前频道的活跃状态
- 不删除 Agent 的注册信息
- Agent 仍然存在于系统中，只是不能在当前频道响应
