# Task Service 部署指南

## 概述

Task Service 是 Agent Team 的核心组件，负责任务管理、Agent 注册和协调。

## 快速启动（开发环境）

```bash
cd task-service
docker-compose up -d
```

访问 http://localhost:8080/docs 查看 API 文档。

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

### 2. API 认证（可选）

如需添加 API Key 认证，可在 `app.py` 中添加：

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

# 保护敏感端点
@app.post("/tasks", dependencies=[Depends(verify_api_key)])
async def create_task(...):
    ...
```

### 3. 速率限制

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/tasks/{task_id}/claim")
@limiter.limit("10/minute")
async def claim_task(...):
    ...
```

## 监控与日志

### 1. 日志收集

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

### 2. 健康检查

```bash
# 检查服务状态
curl http://localhost:8080/

# 预期响应
{"status": "ok", "service": "task-management", "version": "1.1.0"}
```

### 3. 仪表盘

访问 `/dashboard/stats` 查看实时统计：

```bash
curl http://localhost:8080/dashboard/stats | jq
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

2. 检查端口监听
   ```bash
   netstat -tlnp | grep 8080  # Linux
   lsof -i :8080              # macOS
   ```

3. 检查防火墙
   ```bash
   # 测试连接
   curl http://<task-service-ip>:8080/
   ```

4. 检查 Agent 配置
   ```bash
   # 在 Agent 容器中测试
   docker exec <agent-container> curl http://<task-service-ip>:8080/
   ```

### 问题2: 数据库连接失败

```bash
# 检查数据库日志
docker logs taskmanager-db

# 检查连接
psql postgresql://taskmanager:taskmanager@localhost:5432/taskmanager -c "SELECT 1"
```

### 问题3: Agent 显示为 offline

- 检查 Agent 心跳是否正常发送
- 检查 `TASK_SERVICE_URL` 配置是否正确
- 检查网络连接是否稳定

## 性能优化

### 1. 数据库优化

```sql
-- 添加索引（如果还没有）
CREATE INDEX CONCURRENTLY idx_tasks_status_assignee ON tasks(status, assignee_agent);
CREATE INDEX CONCURRENTLY idx_agents_status ON agents(status) WHERE status = 'online';
```

### 2. 连接池配置

```python
# app.py 中调整连接池大小
pool = await asyncpg.create_pool(
    DB_URL,
    min_size=5,      # 最小连接数
    max_size=20      # 最大连接数
)
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

### v1.0 → v1.1

```bash
# 1. 备份数据
docker exec taskmanager-db pg_dump -U taskmanager taskmanager > v1.0_backup.sql

# 2. 拉取新代码
git pull origin main

# 3. 重启服务（会自动执行 migration）
docker-compose down
docker-compose up -d

# 4. 验证
curl http://localhost:8080/
```

## 参考

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [asyncpg 文档](https://magicstack.github.io/asyncpg/)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)
