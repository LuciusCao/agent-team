-- Task Management System Database Schema

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    discord_channel_id VARCHAR(50),
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    title VARCHAR(500) NOT NULL,
    description TEXT,
    task_type VARCHAR(50) NOT NULL CHECK (task_type IN ('research', 'copywrite', 'video', 'review', 'publish')),
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'approval', 'completed', 'failed', 'cancelled')),
    
    assignee_agent VARCHAR(100),
    reviewer_id VARCHAR(100),
    reviewer_mention VARCHAR(100),
    acceptance_criteria TEXT,
    
    parent_task_id INTEGER REFERENCES tasks(id),
    dependencies INTEGER[],
    
    result JSONB,
    feedback TEXT,
    
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    due_at TIMESTAMP,
    completed_at TIMESTAMP
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

-- Agent 注册表
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    discord_user_id VARCHAR(100),
    role VARCHAR(50) CHECK (role IN ('research', 'copywrite', 'video', 'coordinator')),
    status VARCHAR(20) DEFAULT 'offline' CHECK (status IN ('online', 'offline')),
    capabilities JSONB,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_agents_name ON agents(name);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_agent);
CREATE INDEX idx_tasks_reviewer ON tasks(reviewer_id);
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);

-- Agent 活跃频道表
CREATE TABLE IF NOT EXISTS agent_channels (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    last_seen TIMESTAMP DEFAULT NOW(),
    UNIQUE(agent_name, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_channels_agent ON agent_channels(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_channels_channel ON agent_channels(channel_id);
