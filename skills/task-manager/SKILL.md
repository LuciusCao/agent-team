---
name: task-manager
description: 任务管理系统 - 用于创建、更新、查询任务，支持项目绑定和验收流程
metadata:
  {
    openclaw: { emoji: "📋", triggers: ["任务", "task", "创建任务", "查看任务"] },
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

## API 服务

服务地址: `http://localhost:8080`

## 工具函数

### 1. 创建项目

```python
POST /projects
Body: {"name": "项目名", "discord_channel_id": "频道ID", "description": "描述"}
```

### 2. 创建任务

```python
POST /tasks
Body: {
  "project_id": 1,
  "title": "任务标题",
  "description": "任务描述",
  "task_type": "research|copywrite|video|review|publish",
  "assignee_agent": "researcher",
  "reviewer_id": "用户ID",
  "reviewer_mention": "@用户名",
  "acceptance_criteria": "验收标准",
  "dependencies": [1, 2],
  "due_at": "2026-02-25T18:00:00",
  "created_by": "用户"
}
```

### 3. 查询任务

```python
# 列表
GET /tasks?project_id=1&status=pending

# 详情
GET /tasks/{task_id}
```

### 4. 更新任务

```python
PATCH /tasks/{task_id}
Body: {
  "status": "running|completed|failed|cancelled",
  "result": {"output": "结果内容"},
  "assignee_agent": "agent-name"
}
```

### 5. 验收任务

```python
POST /tasks/{task_id}/review
Body: {
  "approved": true|false,
  "feedback": "反馈内容（如果不通过需要详细说明）"
}
```

## Discord 消息模板

Agent 在调用 API 后，需要自行构造并发送 Discord 消息：

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

用户: "创建一个调研任务，调研 AI 助手的最新发展"

1. 调用 POST /projects 获取或创建项目
2. 调用 POST /tasks 创建任务
3. 构造 Discord 消息通知负责人
