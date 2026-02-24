-- Task Management System Database Schema
-- v1.0 - Initial
-- v1.1 - Agent Workforce Extensions

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    discord_channel_id VARCHAR(50),
    description TEXT,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 任务表 (扩展版本)
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    title VARCHAR(500) NOT NULL,
    description TEXT,
    -- 扩展: 更灵活的任务类型
    task_type VARCHAR(50) NOT NULL CHECK (task_type IN ('research', 'copywrite', 'video', 'review', 'publish', 'analysis', 'design', 'development', 'testing', 'deployment', 'coordination')),
    
    -- 扩展: 更细粒度的状态
    status VARCHAR(50) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'assigned', 'running', 'reviewing', 'completed', 'failed', 'cancelled', 'rejected')),
    
    -- 扩展: 优先级
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    
    assignee_agent VARCHAR(100),
    reviewer_id VARCHAR(100),
    reviewer_mention VARCHAR(100),
    acceptance_criteria TEXT,
    
    parent_task_id INTEGER REFERENCES tasks(id),
    dependencies INTEGER[],
    
    -- 扩展: 任务标签
    task_tags TEXT[],
    
    -- 扩展: 预计工时
    estimated_hours FLOAT,
    
    -- 扩展: 任务超时（分钟），NULL 表示使用默认值
    timeout_minutes INTEGER,
    
    -- 扩展: 重试机制
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    result JSONB,
    feedback TEXT,
    
    -- 扩展: 详细时间跟踪
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    assigned_at TIMESTAMP,
    started_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    due_at TIMESTAMP
);

-- 任务日志表
CREATE TABLE IF NOT EXISTS task_logs (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    actor VARCHAR(100),
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Agent 注册表 (扩展版本)
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    discord_user_id VARCHAR(100),
    -- 扩展: 更灵活的角色
    role VARCHAR(50) CHECK (role IN ('research', 'copywrite', 'video', 'coordinator', 'reviewer', 'developer', 'designer', 'tester', 'project_manager')),
    status VARCHAR(20) DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'busy')),
    capabilities JSONB,
    
    -- 扩展: 技能标签
    skills TEXT[],
    
    -- 扩展: 统计数据
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    success_rate FLOAT DEFAULT 0.0,
    
    -- 扩展: 当前任务
    current_task_id INTEGER,
    
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Agent 活跃频道表
CREATE TABLE IF NOT EXISTS agent_channels (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    last_seen TIMESTAMP DEFAULT NOW(),
    UNIQUE(agent_name, channel_id)
);

-- 任务类型默认配置表
CREATE TABLE IF NOT EXISTS task_type_defaults (
    task_type VARCHAR(50) PRIMARY KEY,
    timeout_minutes INTEGER DEFAULT 120,
    max_retries INTEGER DEFAULT 3,
    priority INTEGER DEFAULT 5,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 插入默认配置
INSERT INTO task_type_defaults (task_type, timeout_minutes, max_retries, priority) VALUES
    ('research', 120, 3, 5),
    ('copywrite', 60, 3, 5),
    ('video', 240, 3, 5),
    ('review', 30, 2, 8),
    ('publish', 30, 2, 7),
    ('analysis', 90, 3, 5),
    ('design', 180, 3, 5),
    ('development', 180, 3, 5),
    ('testing', 120, 3, 5),
    ('deployment', 60, 2, 7),
    ('coordination', 60, 2, 6)
ON CONFLICT (task_type) DO NOTHING;

-- ========== v1.1 Migration: Add columns if upgrading ==========

-- 任务表扩展字段
DO $$
BEGIN
    -- 检查并添加 priority 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'priority') THEN
        ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10);
    END IF;
    
    -- 检查并添加 task_tags 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'task_tags') THEN
        ALTER TABLE tasks ADD COLUMN task_tags TEXT[];
    END IF;
    
    -- 检查并添加 estimated_hours 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'estimated_hours') THEN
        ALTER TABLE tasks ADD COLUMN estimated_hours FLOAT;
    END IF;
    
    -- 检查并添加 timeout_minutes 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'timeout_minutes') THEN
        ALTER TABLE tasks ADD COLUMN timeout_minutes INTEGER;
    END IF;
    
    -- 检查并添加 retry_count 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'retry_count') THEN
        ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0;
    END IF;
    
    -- 检查并添加 max_retries 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'max_retries') THEN
        ALTER TABLE tasks ADD COLUMN max_retries INTEGER DEFAULT 3;
    END IF;
    
    -- 检查并添加 assigned_at 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'assigned_at') THEN
        ALTER TABLE tasks ADD COLUMN assigned_at TIMESTAMP;
    END IF;
    
    -- 检查并添加 started_at 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'tasks' AND column_name = 'started_at') THEN
        ALTER TABLE tasks ADD COLUMN started_at TIMESTAMP;
    END IF;
END $$;

-- Agent 表扩展字段
DO $$
BEGIN
    -- 检查并添加 skills 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'skills') THEN
        ALTER TABLE agents ADD COLUMN skills TEXT[];
    END IF;
    
    -- 检查并添加 total_tasks 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'total_tasks') THEN
        ALTER TABLE agents ADD COLUMN total_tasks INTEGER DEFAULT 0;
    END IF;
    
    -- 检查并添加 completed_tasks 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'completed_tasks') THEN
        ALTER TABLE agents ADD COLUMN completed_tasks INTEGER DEFAULT 0;
    END IF;
    
    -- 检查并添加 failed_tasks 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'failed_tasks') THEN
        ALTER TABLE agents ADD COLUMN failed_tasks INTEGER DEFAULT 0;
    END IF;
    
    -- 检查并添加 success_rate 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'success_rate') THEN
        ALTER TABLE agents ADD COLUMN success_rate FLOAT DEFAULT 0.0;
    END IF;
    
    -- 检查并添加 current_task_id 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'agents' AND column_name = 'current_task_id') THEN
        ALTER TABLE agents ADD COLUMN current_task_id INTEGER;
    END IF;
END $$;

-- 项目表扩展字段
DO $$
BEGIN
    -- 检查并添加 status 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'projects' AND column_name = 'status') THEN
        ALTER TABLE projects ADD COLUMN status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'cancelled'));
    END IF;
END $$;

-- 索引
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_skills ON agents USING GIN(skills);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_task_tags ON tasks USING GIN(task_tags);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_agent);
CREATE INDEX IF NOT EXISTS idx_tasks_reviewer ON tasks(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_channels_agent ON agent_channels(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_channels_channel ON agent_channels(channel_id);
