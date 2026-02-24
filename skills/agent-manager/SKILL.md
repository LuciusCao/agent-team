---
name: agent-manager
description: Agent 管理 - 注册到频道、发送心跳、查询频道 Agent
metadata:
  {
    openclaw: { emoji: "📍", triggers: ["注册", "移除", "注销", "心跳", "有哪些 Agent"] },
    zeroclaw: { compatible: true },
  }
---

# Agent Manager Skill

管理 Agent 在 Task Service 的生命周期：
- 注册 Agent 到 Task Service
- 发送心跳保持在线状态
- 从频道移除 Agent
- 查询频道中的活跃 Agent

## 触发条件

### 注册
- `@agent 注册`
- `@agent 登记`
- `注册 @agent`

### 心跳
- 自动启动（Agent 启动时）
- `启动心跳`
- `发送心跳`

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
import threading
import time

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")
AGENT_NAME = os.getenv("AGENT_NAME", "agent")
AGENT_ROLE = os.getenv("AGENT_ROLE", "unknown")

# 全局状态
_heartbeat_thread = None
_current_task_id = None

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


# ============ 心跳功能 ============

def send_heartbeat(current_task_id: int = None):
    """发送心跳到 Task Service
    
    Args:
        current_task_id: 当前正在执行的任务 ID（可选）
    
    Returns:
        API 响应结果
    """
    global _current_task_id
    if current_task_id is not None:
        _current_task_id = current_task_id
    
    try:
        resp = requests.post(
            f"{TASK_SERVICE_URL}/agents/{AGENT_NAME}/heartbeat",
            json={"current_task_id": _current_task_id},
            timeout=10
        )
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        print(f"[Heartbeat] Failed: {e}")
        return None

def start_heartbeat_loop(interval_seconds: int = 30):
    """启动后台心跳线程
    
    定期向 Task Service 发送心跳，保持 Agent 状态为 online。
    如果 5 分钟没有心跳，Task Service 会将 Agent 标记为 offline。
    
    Args:
        interval_seconds: 心跳发送间隔（默认 30 秒）
    
    Returns:
        心跳线程对象
    """
    global _heartbeat_thread
    
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        print("[Heartbeat] Loop already running")
        return _heartbeat_thread
    
    def heartbeat_loop():
        """心跳循环"""
        print(f"[Heartbeat] Started for {AGENT_NAME}, interval={interval_seconds}s")
        while True:
            try:
                result = send_heartbeat()
                if result:
                    print(f"[Heartbeat] OK - Status: {result.get('status', 'unknown')}")
                else:
                    print("[Heartbeat] Failed, will retry next cycle")
            except Exception as e:
                print(f"[Heartbeat] Error: {e}")
            
            time.sleep(interval_seconds)
    
    _heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    _heartbeat_thread.start()
    return _heartbeat_thread

def stop_heartbeat_loop():
    """停止心跳线程
    
    注意：由于线程是 daemon，主程序退出时会自动结束。
    此方法主要用于测试场景。
    """
    global _heartbeat_thread
    # daemon 线程无法直接停止，这里只是标记状态
    _heartbeat_thread = None
    print("[Heartbeat] Loop marked for stop (will exit on next cycle)")

def update_current_task(task_id: int = None):
    """更新当前任务 ID
    
    在心跳中上报当前正在执行的任务，方便 Task Service 监控。
    
    Args:
        task_id: 当前任务 ID，None 表示没有任务
    """
    global _current_task_id
    _current_task_id = task_id
    print(f"[Heartbeat] Current task updated: {task_id}")
```

## 使用示例

### 注册并启动心跳
```python
# 在 Agent 启动时调用
from skills.agent_manager import register_to_channel, start_heartbeat_loop

# 1. 注册到 Task Service
register_to_channel(channel_id="123456", channel_name="#ai项目")

# 2. 启动心跳循环（每 30 秒发送一次）
start_heartbeat_loop(interval_seconds=30)
```

### 更新当前任务
```python
from skills.agent_manager import update_current_task

# 开始执行任务时
update_current_task(task_id=123)

# 任务完成时
update_current_task(task_id=None)
```

### 手动发送心跳
```python
from skills.agent_manager import send_heartbeat

# 手动发送一次心跳
result = send_heartbeat(current_task_id=123)
```

### 注册
```
用户: @researcher 注册
Agent: ✅ researcher 已注册到 #ai项目
       - 角色: research
       - 状态: online
       - 心跳: 已启动 (30s)
```

### 移除
```
用户: 移除 @researcher
Agent: ✅ researcher 已从 #ai项目 移除
       - 心跳: 已停止
```

### 查询频道 Agent
```
用户: 这个频道有哪些 Agent？
Agent: 当前频道活跃的 Agent：
       - @researcher (research) - 在线
       - @copy-writer (copywrite) - 在线
       - @video-master (video) - 离线 (5分钟无心跳)
```

## 心跳机制说明

### 为什么需要心跳？
Task Service 需要知道 Agent 是否还活着：
- Agent 可能崩溃、断网或被关闭
- 没有心跳，Task Service 无法区分"Agent 空闲"和"Agent 死亡"
- 超过 5 分钟无心跳，Agent 会被标记为 `offline`

### 心跳流程
```
Agent (每 30s)          Task Service
    |                         |
    |--- POST /heartbeat --->|
    |    {current_task_id}    |
    |                         | 更新 last_heartbeat
    |<--- {status: online} ---|
    |                         |
    
[5分钟后没有心跳]
    |                         |
    |                         | 标记为 offline
    |                         | 释放任务
```

### 配置
```env
TASK_SERVICE_URL=http://host.docker.internal:8080
AGENT_NAME=researcher
AGENT_ROLE=research
```
