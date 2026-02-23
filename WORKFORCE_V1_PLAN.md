# Agent Workforce v1 - 功能扩展计划

## 当前已有功能

### Task Service (FastAPI + PostgreSQL)
- ✅ 项目创建、查询
- ✅ 任务 CRUD
- ✅ Agent 注册、心跳、上下线
- ✅ 任务认领 (claim)、释放 (release)
- ✅ 任务状态更新
- ✅ 任务验收 (review)
- ✅ Agent 频道活跃记录
- ✅ 任务日志

### Skills
- ✅ agent-register/unregister
- ✅ task-manager

## 需要添加的功能

### 1. 依赖检查机制
- 任务创建时指定 dependencies
- 认领任务前检查依赖是否完成
- 依赖未完成的任务不能认领

### 2. 项目经理 (Project Manager) Agent
- 自动理解项目需求
- 拆分任务并创建子任务
- 监控项目进度
- 重新分配停滞任务

### 3. Reviewer 验收增强
- 基于验收标准逐项检查
- Pass/Partial/Reject 三档结果
- Reject 自动打回并保留反馈

### 4. 任务重试机制
- 失败任务自动重试（带计数）
- 超过重试次数标记为 failed
- 卡住任务（超时）自动释放

### 5. Web Dashboard
- 项目看板
- 任务状态实时更新
- Agent 在线状态
- 统计图表

### 6. 技能匹配
- Agent 技能标签
- 任务类型标签
- 自动推荐/筛选合适 Agent

## 数据库 Schema 扩展

### tasks 表扩展
```sql
-- 新增字段
priority INTEGER DEFAULT 5,           -- 优先级 1-10
dependencies INTEGER[],               -- 依赖任务ID数组
retry_count INTEGER DEFAULT 0,        -- 重试次数
max_retries INTEGER DEFAULT 3,        -- 最大重试次数
task_tags TEXT[],                     -- 任务标签
estimated_hours FLOAT,                -- 预计工时
started_at TIMESTAMP,                 -- 开始时间
}
```

### agents 表扩展
```sql
-- 新增字段
skills TEXT[],                        -- 技能标签
total_tasks INTEGER DEFAULT 0,        -- 完成任务数
success_rate FLOAT DEFAULT 0.0,       -- 成功率
current_task_id INTEGER,              -- 当前任务ID
}
```

## API 扩展

### 新端点
- `GET /tasks/available-for/{agent_name}` - 获取适合某Agent的任务（带技能匹配）
- `POST /projects/{id}/breakdown` - 项目拆分任务
- `GET /projects/{id}/progress` - 项目进度统计
- `POST /tasks/{id}/retry` - 重试失败任务
- `GET /dashboard/stats` - 仪表盘统计数据

## 开发计划

1. **Phase 1**: 数据库扩展 + API 增强
2. **Phase 2**: 依赖检查 + 任务重试
3. **Phase 3**: 技能匹配 + Agent 推荐
4. **Phase 4**: Web Dashboard
5. **Phase 5**: Project Manager Agent Skill
