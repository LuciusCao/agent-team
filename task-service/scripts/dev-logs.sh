#!/bin/bash
#
# dev-logs.sh - 查看开发日志
#
# 用法: ./scripts/dev-logs.sh [选项] [服务名]
#   -f, --follow    持续跟踪日志
#   -n N            显示最后 N 行（默认 100）
#   --since TIME    显示某个时间之后的日志
#   -h, --help      显示帮助
#
# 示例:
#   ./scripts/dev-logs.sh                    # 显示 task-service 最后 100 行
#   ./scripts/dev-logs.sh -f                 # 跟踪 task-service 日志
#   ./scripts/dev-logs.sh -f postgres        # 跟踪 postgres 日志
#   ./scripts/dev-logs.sh -n 50              # 显示最后 50 行
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 检测 docker compose 命令
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "错误: 未找到 docker compose 命令"
    exit 1
fi

# 默认配置
SERVICE="task-service"
FOLLOW=false
LINES=100
SINCE=""

# 颜色定义
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# 显示帮助
show_help() {
    cat << 'EOF'
用法: ./scripts/dev-logs.sh [选项] [服务名]

选项:
    -f, --follow    持续跟踪日志
    -n N            显示最后 N 行（默认 100）
    --since TIME    显示某个时间之后的日志（如 5m, 1h）
    -h, --help      显示帮助

服务名:
    task-service    任务服务（默认）
    postgres        数据库

示例:
    ./scripts/dev-logs.sh                    # 显示 task-service 最后 100 行
    ./scripts/dev-logs.sh -f                 # 跟踪 task-service 日志
    ./scripts/dev-logs.sh -f postgres        # 跟踪 postgres 日志
    ./scripts/dev-logs.sh -n 50              # 显示最后 50 行
    ./scripts/dev-logs.sh --since 5m         # 显示最近 5 分钟的日志
EOF
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n)
            LINES="$2"
            shift 2
            ;;
        --since)
            SINCE="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -*)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
        *)
            SERVICE="$1"
            shift
            ;;
    esac
done

# 构建命令
CMD="$DOCKER_COMPOSE logs"

if [ "$FOLLOW" = true ]; then
    CMD="$CMD -f"
fi

CMD="$CMD --tail=$LINES"

if [ -n "$SINCE" ]; then
    CMD="$CMD --since=$SINCE"
fi

CMD="$CMD $SERVICE"

log_info "查看 $SERVICE 日志..."
$CMD
