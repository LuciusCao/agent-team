# Task Service 部署指南

## 概述

Task Service 是 Agent Team 的核心组件，负责任务管理、Agent 注册和协调。

## 快速启动（开发环境）

```bash
cd task-service
docker-compose up -d
```

访问 http://localhost:8080/docs 查看 API 文档。

访问 http://localhost:8080/health 查看健康检查。

## 部署场景

### 场景1: 单机开发（所有 Agent 在同一台机器）

```yaml
# docker-compose.yml 默认配置即可
services:
  task-service:
    ports:
      - "127.0.0.1:8080:8080"  # 仅本机访问
```

Agent 配置：
```env
TASK_SERVICE_URL=http://host.docker.internal:8080
```

### 场景2: 局域网部署（Agent 在不同设备）

**Task Service 主机：**

```yaml
# docker-compose.yml
services:
  task-service:
    ports:
      - "0.0.0.0:8080:8080"  # 监听所有网卡
    environment:
      - DATABASE_URL=postgresql://taskmanager:taskmanager@postgres:5432/taskmanager
```

```bash
# 获取本机 IP
ipconfig getifaddr en0  # macOS
hostname -I             # Linux
```

**Agent 设备配置：**

```env
# .env
TASK_SERVICE_URL=http://192.168.1.100:8080  # Task Service 主机 IP
```

### 场景3: 云服务器部署（生产环境）

#### 1. 基础部署

```bash
# 克隆代码
git clone https://github.com/LuciusCao/agent-team.git
cd agent-team/task-service

# 启动
docker-compose up -d
```

#### 2. Nginx 反向代理（HTTPS）

```nginx
# /etc/nginx/sites-available/task-service
server {
    listen 443 ssl http2;
    server_name task.your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name task.your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/task-service /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 3. 防火墙配置

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp

# CentOS (firewalld)
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

**Agent 配置：**

```env
TASK_SERVICE_URL=https://task.your-domain.com
```

### 场景4: Kubernetes 部署

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: task-service
  template:
    metadata:
      labels:
        app: task-service
    spec:
      containers:
      - name: task-service
        image: agent-team/task-service:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: task-service
spec:
  selector:
    app: task-service
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## 环境变量配置

| 变量名 | 说明 | 默认值 | 生产环境建议 |
|--------|------|--------|--------------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://localhost:5432/taskmanager` | 使用强密码 |
| `API_KEY` | API 认证密钥 | 无（不认证） | **必须设置** |
| `CORS_ORIGINS` | 允许的 CORS 来源 | `*`（允许所有） | 设置为具体域名 |
| `LOG_LEVEL` | 日志级别 | `INFO` | `WARNING` |
| `MAX_CONCURRENT_TASKS_PER_AGENT` | Agent 最大并发任务数 | `3` | 根据资源调整 |
| `RATE_LIMIT_MAX_REQUESTS` | 每 IP 每分钟最大请求数 | `100` | 根据负载调整 |
| `DEFAULT_TASK_TIMEOUT_MINUTES` | 默认任务超时时间 | `120` | 根据任务类型调整 |

### CORS 配置示例

```bash
# 开发环境（允许所有来源）
CORS_ORIGINS=*

# 生产环境（限制具体域名）
CORS_ORIGINS=https://app.your-domain.com,https://admin.your-domain.com
```

## 安全配置

### 1. 数据库安全

```yaml
# docker-compose.yml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # 使用环境变量
    volumes:
      - postgres-data:/var/lib/postgresql/data
    # 不暴露端口到宿主机，仅内部访问
    # ports:
    #   - "5432:5432"  # 生产环境不要暴露
```

### 2. API 认证（生产环境必须）

API Key 认证已内置，通过环境变量启用：

```bash
# 生成强密码
openssl rand -base64 32

# 设置环境变量
export API_KEY=your-generated-api-key
```

在请求头中添加认证：
```bash
curl -H "X-API-Key: your-generated-api-key" http://localhost:8080/tasks
```

### 3. 速率限制

内置内存速率限制（基于 IP）：

```python
# 可通过环境变量配置
RATE_LIMIT_MAX_REQUESTS=100  # 每 IP 每分钟最大请求数
```

生产环境建议使用 Redis 实现分布式限流：

```python
# 需要额外安装和配置 Redis
# 详见 utils.py 中的 RateLimiter 类
```

## 监控与日志

### 1. 健康检查

```bash
# 基础健康检查
curl http://localhost:8080/
# {"status": "ok", "service": "task-management", "version": "1.2.0"}

# 详细健康检查
curl http://localhost:8080/health
# {
#   "status": "healthy",
#   "version": "1.2.0",
#   "timestamp": "2026-02-24T14:30:00Z",
#   "database": "connected",
#   "uptime_seconds": 3600
# }
```

### 2. 结构化日志

服务使用 JSON 格式日志，便于日志收集和分析：

```json
{
  "timestamp": "2026-02-24T14:30:00Z",
  "level": "INFO",
  "logger": "task_service",
  "message": "Task 123 claimed by agent-1",
  "task_id": 123,
  "agent_name": "agent-1",
  "action": "task_claimed"
}
```

日志收集配置：
```yaml
# docker-compose.yml
services:
  task-service:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        labels: "service"
        env: "OS_VERSION"
```

### 3. 请求日志

所有 HTTP 请求自动记录：
```json
{
  "timestamp": "2026-02-24T14:30:00Z",
  "level": "INFO",
  "method": "POST",
  "path": "/tasks/123/claim",
  "status_code": 200,
  "duration_ms": 45.2,
  "client_ip": "192.168.1.100",
  "action": "http_request"
}
```

### 4. 仪表盘

访问 `/dashboard/stats` 查看实时统计：

```bash
curl http://localhost:8080/dashboard/stats | jq
```

响应示例：
```json
{
  "projects": {"total": 5, "active": 3},
  "tasks": {
    "total": 50,
    "pending": 10,
    "assigned": 5,
    "running": 3,
    "reviewing": 2,
    "completed": 28,
    "failed": 1,
    "rejected": 1
  },
  "agents": {"total": 5, "online": 4, "offline": 0, "busy": 3}
}
```

## 备份与恢复

### 数据库备份

```bash
# 备份
docker exec taskmanager-db pg_dump -U taskmanager taskmanager > backup.sql

# 恢复
docker exec -i taskmanager-db psql -U taskmanager taskmanager < backup.sql
```

### 自动备份脚本

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

docker exec taskmanager-db pg_dump -U taskmanager taskmanager | gzip > "$BACKUP_DIR/backup_$DATE.sql.gz"

# 保留最近 7 天的备份
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

```bash
# 添加到 crontab
crontab -e
# 每天凌晨 2 点备份
0 2 * * * /path/to/backup.sh
```

## 故障排查

### 问题1: Agent 无法连接 Task Service

**检查步骤：**

1. 检查服务是否运行
   ```bash
   docker ps | grep task-service
   ```

2. 检查健康状态
   ```bash
   curl http://<task-service-ip>:8080/health
   ```

3. 检查端口监听
   ```bash
   netstat -tlnp | grep 8080  # Linux
   lsof -i :8080              # macOS
   ```

4. 检查防火墙
   ```bash
   # 测试连接
   curl http://<task-service-ip>:8080/
   ```

5. 检查 Agent 配置
   ```bash
   # 在 Agent 容器中测试
   docker exec <agent-container> curl http://<task-service-ip>:8080/health
   ```

### 问题2: 数据库连接失败

```bash
# 检查数据库日志
docker logs taskmanager-db

# 检查连接
psql postgresql://taskmanager:taskmanager@localhost:5432/taskmanager -c "SELECT 1"

# 检查连接池状态（在日志中查看）
docker logs task-service | grep -i "db_retry\|connection"
```

### 问题3: Agent 显示为 offline

- 检查 Agent 心跳是否正常发送
- 检查 `TASK_SERVICE_URL` 配置是否正确
- 检查网络连接是否稳定
- 查看 Task Service 日志中的心跳记录

### 问题4: 幂等性失效

幂等键现在持久化到数据库，服务重启后仍然有效：

```sql
-- 查看幂等键
SELECT * FROM idempotency_keys ORDER BY created_at DESC LIMIT 10;

-- 清理过期幂等键（自动清理，也可手动执行）
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours';
```

## 性能优化

### 1. 数据库优化

```sql
-- 添加索引（如果还没有）
CREATE INDEX CONCURRENTLY idx_tasks_status_assignee ON tasks(status, assignee_agent);
CREATE INDEX CONCURRENTLY idx_agents_status ON agents(status) WHERE status = 'online';
CREATE INDEX CONCURRENTLY idx_idempotency_keys_created_at ON idempotency_keys(created_at);
```

### 2. 连接池配置

```python
# 通过环境变量或修改 app.py
# 当前配置（可根据负载调整）：
# min_size=2, max_size=10
```

### 3. 缓存（可选）

对于高频查询的端点，可添加 Redis 缓存：

```python
import redis
r = redis.Redis(host='redis', port=6379)

@app.get("/dashboard/stats")
async def get_dashboard_stats():
    # 尝试从缓存获取
    cached = r.get("dashboard_stats")
    if cached:
        return json.loads(cached)
    
    # 查询数据库
    stats = await compute_stats()
    
    # 缓存 60 秒
    r.setex("dashboard_stats", 60, json.dumps(stats))
    return stats
```

## 升级指南

### v1.1 → v1.2

**主要变更：**
- 新增 `/health` 健康检查端点
- 幂等键持久化到数据库
- 添加数据库连接重试机制
- CORS 来源可配置
- 结构化日志改进

**升级步骤：**

```bash
# 1. 备份数据
docker exec taskmanager-db pg_dump -U taskmanager taskmanager > v1.1_backup.sql

# 2. 拉取新代码
git pull origin main

# 3. 重启服务（会自动执行 migration）
docker-compose down
docker-compose up -d

# 4. 验证
 curl http://localhost:8080/health
```

## API 变更日志

### v1.2.0

**新增端点：**
- `GET /health` - 详细健康检查

**改进：**
- 幂等性键持久化到数据库
- 数据库连接自动重试
- 请求日志中间件
- CORS 来源可配置

**废弃：**
- 内存中的幂等性存储（已迁移到数据库）

## 参考

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [asyncpg 文档](https://magicstack.github.io/asyncpg/)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)
- [项目 README](../README.md)