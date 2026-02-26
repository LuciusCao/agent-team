# Changelog

所有重要的变更都会记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### Fixed

#### 循环依赖检测算法优化 (2026-02-26)

**问题描述：**
原 `check_circular_dependency` 函数使用全局 `visited` 集合来避免重复访问，这导致合法的共享依赖被误判为循环依赖。

**错误场景：**
```
任务 C（基础任务）
  ↑
任务 A ← 任务 B

当检查 "任务 B 依赖任务 A" 时：
- B → A → C（标记 A, C 为 visited）
- 如果 C 还有其他依赖，会被误判为循环
```

**解决方案：**
- 改用 DFS + `path` 集合来检测是否会回到 `task_id`
- 每个新依赖单独检查，避免分支间干扰
- 只关心是否会形成回到当前任务的循环，不关心依赖图中其他循环

**代码变更：**
- `utils.py`: 重写 `check_circular_dependency` 函数
- `tests/test_app.py`: 新增两个测试用例
  - `test_check_circular_dependency_shared_dependency`: 验证菱形结构不形成循环
  - `test_check_circular_dependency_self_reference`: 验证自引用检测

**文档更新：**
- `README.md`: 添加任务依赖管理章节
- `tests/README.md`: 更新测试分类说明

### Changed

#### 测试数据库初始化优化 (2026-02-26)

**问题描述：**
测试数据库在模块导入时初始化，如果数据库连接失败会导致整个测试模块无法导入。

**解决方案：**
- 添加 `_test_db_initialized` 标志避免重复初始化
- 添加 try-except 包装，失败时不阻止模块导入
- 延迟错误到实际运行时处理

**代码变更：**
- `tests/test_app.py`: 重构 `init_test_database` 函数

## [1.2.0] - 2026-02-26

### Added

- 速率限制器内存泄漏修复（添加 `max_store_size` 限制和强制清理）
- 循环依赖检测功能
- 优雅关闭机制（后台任务可中断）
- 数据库连接池错误计数器（避免频繁重置）
- 完整测试覆盖（350+ 行测试代码）
- 脚手架脚本支持 uv 和 ruff

### Changed

- 重构项目结构
- 更新 API 文档
- 修复 Docker 部署问题

## [1.1.0] - 2026-02-25

### Added

- 软删除功能（tasks, agents, projects）
- 后台任务监控（heartbeat, stuck_task, cleanup）
- 幂等性支持（idempotency keys）
- 任务依赖管理
- Agent 统计信息

### Changed

- 优化数据库连接池配置
- 改进错误处理和日志记录

## [1.0.0] - 2026-02-24

### Added

- 初始版本发布
- 任务管理核心功能
- Agent 注册和心跳
- 项目管理和拆分
- RESTful API
