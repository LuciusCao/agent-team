# Agent-Team Dev 分支深度代码审查报告

**审查日期**: 2026-02-25  
**审查分支**: dev  
**审查范围**: task-service 完整代码库  
**审查标准**: code-reviewer SKILL.md Phase 1-5

---

## 📊 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 功能完整性 | ⭐⭐⭐⭐⭐ | 功能完整，覆盖任务生命周期全流程 |
| 代码质量 | ⭐⭐⭐⭐☆ | 整体良好，存在少量代码重复和边界问题 |
| 安全 | ⭐⭐⭐⭐☆ | 基础安全措施到位，部分边界需加强 |
| 性能 | ⭐⭐⭐⭐☆ | 有优化意识，部分查询可进一步优化 |
| 可维护性 | ⭐⭐⭐⭐☆ | 模块化良好，但存在代码重复问题 |

---

## 🔴 Critical 问题（必须修复）

### 1. 代码重复严重 - DRY 原则违反

**问题描述**: 相同的功能在多个地方重复实现，导致维护困难和潜在的不一致性。

**具体位置**:

1. **CORS 配置重复** (`app.py` 和 `main.py`)
   ```python
   # app.py 第 85-96 行
   # main.py 第 35-46 行
   # 完全相同的 CORS 配置代码
   ```

2. **请求日志中间件重复**
   ```python
   # app.py 第 102-140 行
   # main.py 第 52-90 行
   # 完全相同的中间件实现
   ```

3. **健康检查端点重复**
   ```python
   # app.py 第 175-198 行
   # main.py 第 96-114 行
   ```

4. **后台任务重复**
   ```python
   # app.py 第 723-795 行 (heartbeat_monitor, stuck_task_monitor)
   # background.py 完整文件
   # 两个地方都有相同的后台任务实现
   ```

5. **API 路由重复**
   ```python
   # app.py 包含完整的项目、任务、Agent 端点实现
   # routers/*.py 包含相同的端点实现
   # 两者同时存在，但 main.py 使用的是 routers
   ```

**风险**:
- 修改一处需要同时修改多处，容易遗漏
- 可能导致行为不一致
- 增加维护成本

**建议**:
```bash
# 1. 删除 app.py，只保留 main.py 作为入口
# 2. 确保所有路由只在 routers/ 中实现
# 3. 后台任务只保留 background.py
# 4. 统一从 utils.py 导入共享功能
```

---

### 2. 全局变量 `_pool` 在后台任务中的竞态条件

**问题描述**: `background.py` 和 `app.py` 都使用了全局 `_pool`，但存在初始化竞态。

**代码位置**: `background.py` 第 14 行

```python
# background.py
async def heartbeat_monitor():
    global _pool  # 使用了全局 _pool
    while True:
        await asyncio.sleep(60)
        try:
            pool = await get_pool()  # 可能和 app.py 的 get_db 竞争
```

**问题分析**:
- `app.py` 有自己的 `_pool` 全局变量
- `database.py` 也有自己的 `_pool`
- 后台任务导入的是 `background.py` 中的 `_pool`（未定义！）

**验证**:
```python
# background.py 第 14 行
async def heartbeat_monitor():
    global _pool  # NameError: name '_pool' is not defined
```

**修复建议**:
```python
# background.py 应该导入 database 的 _pool
from database import get_pool, reset_pool, _pool

# 或者更好的方式：不使用 global，每次都调用 get_pool()
async def heartbeat_monitor():
    while True:
        await asyncio.sleep(60)
        try:
            pool = await get_pool()  # 每次都获取
```

---

### 3. 幂等性键清理逻辑存在竞态窗口

**问题描述**: `check_idempotency` 函数先清理过期键，再检查键是否存在，存在竞态窗口。

**代码位置**: `utils.py` 第 81-95 行

```python
async def check_idempotency(conn: asyncpg.Connection, idempotency_key: Optional[str] = None):
    # 先清理
    await conn.execute(
        "DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours'"
    )
    # 再检查 - 这里可能有新插入的键被误删
    row = await conn.fetchrow(...)
```

**问题**:
- 清理和检查不是原子操作
- 在高并发下，可能清理掉刚插入的有效键

**修复建议**:
```python
async def check_idempotency(conn: asyncpg.Connection, idempotency_key: Optional[str] = None):
    if not idempotency_key:
        return None, False
    
    # 只检查，不清理（清理交给后台任务）
    row = await conn.fetchrow(
        "SELECT response FROM idempotency_keys WHERE key = $1 AND created_at > NOW() - INTERVAL '24 hours'",
        idempotency_key
    )
    
    if row:
        return json.loads(row['response']), True
    return None, False
```

---

## 🟠 High 问题（建议修复）

### 4. `app.py` 文件应该被删除

**问题描述**: 项目同时存在 `app.py` 和 `main.py`，且 `main.py` 是实际入口。

**分析**:
- `main.py` 使用了模块化路由 (`routers/`)
- `app.py` 是旧版本，包含重复代码
- 两者同时维护会导致不一致

**建议**:
```bash
# 确认 main.py 可以正常运行后
rm task-service/app.py
```

---

### 5. 速率限制器是内存存储，不支持多实例

**问题描述**: `RateLimiter` 和 `rate_limit_store` 使用内存存储，在多个服务实例间无法共享状态。

**代码位置**: `utils.py` 第 220-270 行, `security.py` 第 12 行

```python
# security.py
rate_limit_store = {}  # 内存存储

# utils.py
class RateLimiter:
    def __init__(self, ...):
        self.store = {}  # 也是内存存储
```

**风险**:
- 水平扩展时，每个实例有自己的计数器
- 用户可以在不同实例间绕过限流

**建议**:
- 短期：添加文档说明此限制
- 长期：使用 Redis 实现分布式限流

---

### 6. 测试文件导入的是 `main` 但实际可能运行 `app`

**问题描述**: `test_app.py` 导入 `from main import app`，但可能存在 `app.py` 的混淆。

**代码位置**: `tests/test_app.py` 第 18 行

```python
from main import app, get_db
```

**建议**:
- 删除 `app.py` 消除混淆
- 或在文档中明确说明入口点是 `main.py`

---

### 7. `success_rate` 计算存在精度问题

**问题描述**: Agent 统计中的 `success_rate` 使用浮点数计算，可能存在精度问题。

**代码位置**: `utils.py` 第 200-210 行

```python
success_rate = (completed_tasks::FLOAT + 1) / NULLIF(total_tasks + 1, 0)
```

**问题**:
- 浮点数精度可能导致显示问题
- 计算逻辑在多处重复

**建议**:
- 使用 `NUMERIC` 类型存储
- 或在应用层计算后存储

---

## 🟡 Medium 问题（值得注意）

### 8. 任务依赖验证的索引问题

**问题描述**: `validate_task_dependencies` 函数接收的是任务列表，但依赖使用的是数组索引，容易出错。

**代码位置**: `utils.py` 第 130-160 行

```python
def validate_task_dependencies(tasks: list) -> None:
    for i, task in enumerate(tasks):
        if task.dependencies:
            for dep_idx in task.dependencies:
                if dep_idx < 0 or dep_idx >= n:  # 检查索引范围
```

**问题**:
- 依赖使用数组索引而不是任务 ID
- 客户端需要知道任务在数组中的位置

**建议**:
- 考虑使用任务 ID 作为依赖标识
- 或添加更清晰的文档说明

---

### 9. 部分 API 端点缺少幂等性支持

**问题描述**: 只有 `claim_task` 和 `submit_task` 实现了幂等性，其他修改操作没有。

**代码位置**: `routers/tasks.py`

**建议**:
- 为以下操作添加幂等性支持：
  - `start_task` - 防止重复开始
  - `release_task` - 防止重复释放
  - `retry_task` - 防止重复重试
  - `review_task` - 防止重复验收

---

### 10. 日志中可能包含敏感信息

**问题描述**: 请求日志中间件记录了所有请求，可能包含敏感信息。

**代码位置**: `main.py` 第 52-90 行

```python
logger.info(
    f"{request.method} {request.url.path} - {response.status_code}...",
    extra={...}
)
```

**问题**:
- 请求体中的敏感信息（如 API Key）可能被记录
- URL 查询参数中的敏感信息可能被记录

**建议**:
```python
# 添加敏感信息过滤
SENSITIVE_FIELDS = ['api_key', 'token', 'password', 'secret']

def sanitize_log_data(data: dict) -> dict:
    return {k: '***' if k.lower() in SENSITIVE_FIELDS else v 
            for k, v in data.items()}
```

---

### 11. `due_at` 字段类型为字符串，缺少验证

**问题描述**: `TaskCreate` 模型中的 `due_at` 是 `Optional[str]`，但没有格式验证。

**代码位置**: `models.py` 第 35 行

```python
due_at: Optional[str] = None
```

**建议**:
```python
from pydantic import Field
from datetime import datetime

due_at: Optional[datetime] = None  # Pydantic 会自动验证 ISO 格式
```

---

### 12. 数据库连接池配置缺少超时设置

**问题描述**: 连接池创建时没有配置连接超时。

**代码位置**: `database.py` 第 16 行

```python
_pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
```

**建议**:
```python
_pool = await asyncpg.create_pool(
    DB_URL, 
    min_size=2, 
    max_size=10,
    command_timeout=60,  # 命令超时
    max_inactive_time=300,  # 连接最大空闲时间
    max_queries=100000,  # 连接最大查询次数
)
```

---

## 🟢 Low 问题（可选优化）

### 13. 部分函数缺少类型注解

**代码示例**:
```python
# routers/tasks.py 第 23 行
async def create_task(task: TaskCreate, db=Depends(get_db)):  # 缺少返回类型
```

### 14. 魔法数字应该提取为常量

**代码示例**:
```python
# utils.py 第 150 行
if dep_idx < 0 or dep_idx >= n:  # 0 是魔法数字

# main.py 第 60 行
await asyncio.sleep(60)  # 60 应该提取为常量 HEARTBEAT_INTERVAL
```

### 15. 部分异常处理过于宽泛

**代码示例**:
```python
# background.py 第 25 行
except Exception as e:  # 过于宽泛
    logger.error(f"Heartbeat monitor error: {e}", exc_info=True)
```

---

## ✅ 做得好的地方

### 1. 数据库操作使用参数化查询
所有 SQL 查询都使用参数化，有效防止 SQL 注入。

### 2. 竞态条件处理得当
`claim_task` 使用 `UPDATE ... RETURNING` 实现乐观锁，避免 SELECT+UPDATE 竞态。

### 3. 结构化日志
使用 JSON 格式日志，便于日志收集和分析。

### 4. 幂等性设计
关键操作（claim、submit）实现了幂等性，防止重复处理。

### 5. 依赖检查
任务依赖检查在 SQL 层面完成，避免 N+1 查询。

### 6. 事务使用
所有数据库操作都使用 `async with db.acquire() as conn`，确保事务性。

### 7. 配置化设计
超时、重试次数等都支持环境变量配置。

### 8. 测试覆盖
测试文件覆盖了完整的任务生命周期、并发测试、幂等性测试。

---

## 📋 修复优先级建议

| 优先级 | 问题 | 估计工时 |
|--------|------|----------|
| P0 | 删除 app.py，统一使用 main.py | 30 分钟 |
| P0 | 修复 background.py 的 `_pool` 引用 | 15 分钟 |
| P1 | 修复幂等性键清理竞态 | 30 分钟 |
| P1 | 为其他操作添加幂等性支持 | 2 小时 |
| P2 | 添加敏感信息过滤 | 1 小时 |
| P2 | 优化数据库连接池配置 | 30 分钟 |
| P3 | 完善类型注解 | 1 小时 |
| P3 | 提取魔法数字为常量 | 30 分钟 |

---

## 🎯 总结

agent-team 的 dev 分支整体代码质量良好，功能完整，安全措施到位。主要问题是**代码重复**（app.py vs main.py）和几个**边界情况处理**。建议优先修复 Critical 和 High 级别的问题，然后进行 Medium 级别的优化。

代码架构清晰，模块化设计良好，测试覆盖全面，是一个可维护的代码库。
