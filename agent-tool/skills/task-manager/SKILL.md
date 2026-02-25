---
name: task-manager
description: 任务管理系统 - 用于创建、更新、查询任务，支持项目绑定和验收流程
metadata:
  {
    openclaw: { emoji: "📋", triggers: ["任务", "task", "创建任务", "查看任务", "我的任务"] },
    zeroclaw: { compatible: true },
  }
---

# Task Manager Skill

管理任务系统，支持创建任务、查询状态、验收等操作。

## 触发条件

用户提及以下关键词时自动激活：
- "创建任务"
- "查看任务"
- "任务列表"
- "更新任务"
- "验收任务"
- "我的任务"

## 配置

在 Agent 的环境变量中配置：

```env
TASK_SERVICE_URL=http://host.docker.internal:8080
```

## 工具函数

```python
import os
import requests
from typing import Optional, List, Dict, Any

TASK_SERVICE_URL = os.getenv("TASK_SERVICE_URL", "http://localhost:8080")

# ============ 项目操作 ============

def create_project(name: str, discord_channel_id: str = None, description: str = None) -> Dict:
    """创建项目"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/projects",
        json={
            "name": name,
            "discord_channel_id": discord_channel_id,
            "description": description
        }
    )
    resp.raise_for_status()
    return resp.json()

def get_project(project_id: int) -> Dict:
    """获取项目详情"""
    resp = requests.get(f"{TASK_SERVICE_URL}/projects/{project_id}")
    resp.raise_for_status()
    return resp.json()

def list_projects() -> List[Dict]:
    """列出所有项目"""
    resp = requests.get(f"{TASK_SERVICE_URL}/projects")
    return resp.json()

# ============ 任务操作 ============

def create_task(
    project_id: int,
    title: str,
    task_type: str,
    description: str = None,
    assignee_agent: str = None,
    reviewer_id: str = None,
    reviewer_mention: str = None,
    acceptance_criteria: str = None,
    parent_task_id: int = None,
    dependencies: List[int] = None,
    created_by: str = None,
    due_at: str = None
) -> Dict:
    """创建任务"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/tasks",
        json={
            "project_id": project_id,
            "title": title,
            "description": description,
            "task_type": task_type,
            "assignee_agent": assignee_agent,
            "reviewer_id": reviewer_id,
            "reviewer_mention": reviewer_mention,
            "acceptance_criteria": acceptance_criteria,
            "parent_task_id": parent_task_id,
            "dependencies": dependencies,
            "created_by": created_by,
            "due_at": due_at
        }
    )
    resp.raise_for_status()
    return resp.json()

def get_task(task_id: int) -> Dict:
    """获取任务详情"""
    resp = requests.get(f"{TASK_SERVICE_URL}/tasks/{task_id}")
    resp.raise_for_status()
    return resp.json()

def list_tasks(project_id: int = None, status: str = None, assignee: str = None) -> List[Dict]:
    """列出任务"""
    params = {}
    if project_id:
        params["project_id"] = project_id
    if status:
        params["status"] = status
    if assignee:
        params["assignee"] = assignee
    
    resp = requests.get(f"{TASK_SERVICE_URL}/tasks", params=params)
    return resp.json()

def update_task(task_id: int, status: str = None, result: Dict = None, assignee_agent: str = None) -> Dict:
    """更新任务状态"""
    data = {}
    if status:
        data["status"] = status
    if result:
        data["result"] = result
    if assignee_agent:
        data["assignee_agent"] = assignee_agent
    
    resp = requests.patch(f"{TASK_SERVICE_URL}/tasks/{task_id}", json=data)
    resp.raise_for_status()
    return resp.json()

def review_task(task_id: int, approved: bool, feedback: str = None) -> Dict:
    """验收任务"""
    resp = requests.post(
        f"{TASK_SERVICE_URL}/tasks/{task_id}/review",
        json={
            "approved": approved,
            "feedback": feedback
        }
    )
    resp.raise_for_status()
    return resp.json()

# ============ Agent 操作 ============

def get_online_agents() -> List[Dict]:
    """获取所有在线 Agent"""
    resp = requests.get(f"{TASK_SERVICE_URL}/agents?status=online")
    return resp.json()

def get_channel_agents(channel_id: str) -> List[Dict]:
    """获取某频道的活跃 Agent"""
    resp = requests.get(f"{TASK_SERVICE_URL}/channels/{channel_id}/agents")
    return resp.json()

def get_agent_channels(agent_name: str) -> List[Dict]:
    """获取 Agent 活跃的所有频道"""
    resp = requests.get(f"{TASK_SERVICE_URL}/agents/{agent_name}/channels")
    return resp.json()

# ============ 工具函数 ============

def get_my_tasks(agent_name: str) -> List[Dict]:
    """获取某 Agent 的待办任务"""
    return list_tasks(status="pending", assignee=agent_name)

def format_task_list(tasks: List[Dict]) -> str:
    """格式化任务列表为 Markdown"""
    if not tasks:
        return "暂无任务"
    
    lines = ["## 📋 任务列表\n"]
    for t in tasks:
        status_emoji = {
            "pending": "⏳",
            "running": "🔄",
            "approval": "✅",
            "completed": "🎉",
            "failed": "❌"
        }.get(t["status"], "❓")
        
        lines.append(f"- {status_emoji} **#{t['id']}** {t['title']}")
        lines.append(f"  - 类型: {t['task_type']} | 状态: {t['status']}")
        if t.get("assignee_agent"):
            lines.append(f"  - 负责: @{t['assignee_agent']}")
        lines.append("")
    
    return "\n".join(lines)
```

## 处理流程

### 创建任务
```
1. 解析用户指令，提取任务信息
2. 确定项目（从频道或名称）
3. 确定负责人（根据 task_type 筛选可用 Agent）
4. 调用 create_task()
5. 发送 Discord 消息通知负责人
```

### 查看任务
```
1. 根据参数查询任务列表
2. 格式化输出为 Markdown
3. 回复用户
```

### 更新任务状态
```
1. 解析用户指令，获取 task_id 和新状态
2. 调用 update_task()
3. 根据新状态决定是否通知相关人
```

### 验收任务
```
1. 解析用户指令，获取 task_id 和验收结果
2. 调用 review_task()
3. 如果不通过，写入详细反馈
4. 如果通过，通知负责人并触发下游任务
```

## Discord 消息模板

### 新任务派发

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

### 任务状态更新

```markdown
## 🔄 任务状态更新
**任务**: {task_title}
**状态**: {old_status} → {new_status}
**负责人**: {assignee}
```

### 申请验收

```markdown
## ✅ 任务完成 - 申请验收
**任务**: {task_title}
**负责人**: {assignee}
**结果**: {result_summary}
**请 {reviewer_mention} 验收**
```

### 验收通过

```markdown
## 🎉 验收通过
**任务**: {task_title}
**验收人**: {reviewer}
**状态**: completed
```

### 验收拒绝

```markdown
## ❌ 验收不通过 - 需修改
**任务**: {task_title}
**验收人**: {reviewer}
**反馈**:
{feedback}

**请 {assignee} 根据反馈修改后重新提交验收**
```

## 使用示例

### 创建任务
```
用户: 创建一个调研任务，调研 AI 助手的最新发展

Agent: 
1. 确认项目
2. 查询可用 researcher
3. 创建任务
4. 回复:
   ## 📋 新任务创建
   **项目**: AI 产品宣传
   **任务**: 调研 AI 助手最新发展
   **类型**: research
   **负责人**: @researcher
   **验收人**: @猫猫侠
   **验收标准**:
   - 列出 3 个主要竞品
   - 每个竞品包含核心功能、定价
```

### 查看我的任务
```
用户: 我的任务有哪些？

Agent: 查询 pending 状态且 assignee = researcher 的任务
回复:
## 📋 任务列表
- ⏳ **#1** 调研 AI 助手最新发展
  - 类型: research | 状态: pending
  - 负责: @researcher
```

### 验收任务
```
用户: 验收任务 1，通过

Agent: 调用 review_task(1, approved=True)
回复:
## 🎉 验收通过
**任务**: 调研 AI 助手最新发展
**验收人**: @猫猫侠
**状态**: completed
```

## 注意事项

1. 所有 HTTP 请求需要处理异常
2. channel_id 可以从 Discord 消息上下文获取
3. 任务状态流转: pending → running → approval → completed/failed
4. 只有 status=approval 的任务才能验收
