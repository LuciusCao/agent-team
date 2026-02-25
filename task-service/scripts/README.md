# Task Service 开发工具脚本

这个目录包含开发过程中常用的工具脚本，帮助快速启动、管理和清理开发环境。

## 快速开始

使用主入口脚本 `dev.sh`：

```bash
./scripts/dev.sh start          # 启动开发环境
./scripts/dev.sh status         # 查看服务状态
./scripts/dev.sh test           # 运行测试
./scripts/dev.sh stop           # 停止服务
```

## 脚本说明

### 🔧 dev.sh - 主入口脚本

统一的命令入口，所有开发操作的起点。

```bash
./scripts/dev.sh <命令> [选项]
```

支持的命令：
- `start` - 启动开发环境
- `stop` - 停止开发环境
- `restart` - 重启开发环境
- `clean` - 清空开发数据
- `logs` - 查看日志
- `test` - 运行测试
- `seed` - 生成测试数据
- `status` - 查看服务状态

### 🚀 dev-start.sh - 启动服务

启动开发环境，支持多种模式。

```bash
# 正常启动
./scripts/dev-start.sh

# 清空数据库后启动（干净环境）
./scripts/dev-start.sh --fresh

# 启动并查看日志
./scripts/dev-start.sh --logs
```

### 🧹 dev-clean.sh - 清理数据

清空开发环境数据，支持不同级别的清理。

```bash
# 清空表数据（保留数据库结构）
./scripts/dev-clean.sh --keep-vol

# 完全清空（包括 Docker 卷）
./scripts/dev-clean.sh --all

# 跳过确认提示
./scripts/dev-clean.sh --all --confirm
```

### 🔄 dev-restart.sh - 重启服务

重启开发环境。

```bash
# 正常重启
./scripts/dev-restart.sh

# 清空后重启
./scripts/dev-restart.sh --clean

# 重启并查看日志
./scripts/dev-restart.sh --logs
```

### 📊 dev-logs.sh - 查看日志

查看服务日志。

```bash
# 显示最后 100 行
./scripts/dev-logs.sh

# 显示最后 50 行
./scripts/dev-logs.sh -n 50

# 持续跟踪日志
./scripts/dev-logs.sh -f

# 查看 postgres 日志
./scripts/dev-logs.sh -f postgres

# 查看最近 5 分钟的日志
./scripts/dev-logs.sh --since 5m
```

### 🧪 dev-test.sh - 运行测试

运行测试套件。

```bash
# 运行所有测试
./scripts/dev-test.sh

# 详细输出
./scripts/dev-test.sh -v

# 只运行特定测试
./scripts/dev-test.sh -k test_create

# 生成覆盖率报告
./scripts/dev-test.sh --cov

# 监视模式（文件变化自动运行）
./scripts/dev-test.sh --watch
```

### 🌱 dev-seed.sh - 生成测试数据

生成开发用的测试数据。

```bash
# 生成默认数据（3项目、3Agent、15任务）
./scripts/dev-seed.sh

# 先清空后生成
./scripts/dev-seed.sh --clean

# 生成更多数据
./scripts/dev-seed.sh --projects 5 --tasks 10 --agents 5
```

## 典型工作流

### 1. 全新开发环境

```bash
# 启动干净环境
./scripts/dev.sh start --fresh

# 生成测试数据
./scripts/dev.sh seed

# 查看状态
./scripts/dev.sh status
```

### 2. 日常开发

```bash
# 启动服务
./scripts/dev.sh start

# 查看日志
./scripts/dev.sh logs -f

# 修改代码后运行测试
./scripts/dev.sh test
```

### 3. 调试问题

```bash
# 重启并查看日志
./scripts/dev.sh restart --logs

# 或者只查看日志
./scripts/dev.sh logs -f
```

### 4. 清理环境

```bash
# 只清空数据
./scripts/dev.sh clean --keep-vol

# 完全重置
./scripts/dev.sh clean --all
```

## 环境变量

脚本使用以下环境变量：

- `API_KEY` - API 认证密钥（用于 seed 脚本）
- `DATABASE_URL` - 数据库连接字符串

可以在 `.env` 文件中配置这些变量。

## 注意事项

1. 所有脚本都需要在 `task-service` 目录下运行
2. 确保 Docker 已安装并运行
3. 首次运行可能需要下载镜像，请耐心等待
4. 使用 `--fresh` 或 `--clean` 会删除数据，请谨慎使用

## 故障排除

### 服务启动失败

```bash
# 查看详细日志
./scripts/dev.sh logs -f

# 完全重置后重试
./scripts/dev.sh clean --all
./scripts/dev.sh start --fresh
```

### 数据库连接失败

```bash
# 检查 postgres 状态
./scripts/dev.sh logs postgres

# 重启服务
./scripts/dev.sh restart
```

### 测试失败

```bash
# 确保服务在运行
./scripts/dev.sh status

# 重新生成测试数据
./scripts/dev.sh seed --clean

# 运行测试
./scripts/dev.sh test -v
```
