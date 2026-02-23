# Task Service Skill

让 Agent 能够从任务池认领任务。

## Commands

### 1. 查看可认领任务
列出所有待认领的任务（pending 状态，没有 assignee）。

```bash
curl -s "http://task-service:8080/tasks/available" | jq '.'
```

### 2. 认领任务
Agent 主动认领一个任务。

```bash
curl -s -X POST "http://task-service:8080/tasks/{task_id}/claim?agent_name=YOUR_AGENT_NAME" \
  -H "Content-Type: application/json"
```

### 3. 释放任务
如果任务做不了，可以释放回任务池。

```bash
curl -s -X POST "http://task-service:8080/tasks/{task_id}/release?agent_name=YOUR_AGENT_NAME" \
  -H "Content-Type: application/json"
```

### 4. 查看我的任务
查看当前 Agent 正在做的任务。

```bash
curl -s "http://task-service:8080/tasks?assignee=YOUR_AGENT_NAME" | jq '.'
```

### 5. 更新任务状态
更新任务进度。

```bash
curl -s -X PATCH "http://task-service:8080/tasks/{task_id}" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed", "result": {"output": "结果内容"}}'
```

## Workflow

1. **查任务** → 调用 `/tasks/available`
2. **认领** → 调用 `/tasks/{id}/claim?agent_name=xxx`
3. **执行** → 完成任务
4. **提交** → 调用 `/tasks/{id}` 更新状态为 completed

## Environment

- `TASK_SERVICE_URL`: 任务服务地址（默认 http://task-service:8080）
- `AGENT_NAME`: 当前 Agent 名称
