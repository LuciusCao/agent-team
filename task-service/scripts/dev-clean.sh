#!/bin/bash
#
# dev-clean.sh - 清空开发环境数据
#
# 用法: ./scripts/dev-clean.sh [选项]
#   --all       清空所有数据（包括卷）
#   --keep-vol  保留 Docker 卷，只清空表数据
#   --confirm   跳过确认提示
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

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 确认提示
confirm() {
    local message="$1"
    echo -e "${YELLOW}$message${NC}"
    read -p "是否继续? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "操作已取消"
        exit 0
    fi
}

# 停止服务
stop_services() {
    log_info "停止服务..."
    $DOCKER_COMPOSE down
}

# 清空所有数据（包括卷）
clean_all() {
    log_warn "这将删除所有容器、网络和卷"
    $DOCKER_COMPOSE down -v --remove-orphans
    
    # 删除构建缓存
    log_info "清理构建缓存..."
    docker system prune -f
    
    log_success "所有数据已清空"
}

# 只清空表数据（保留卷）
clean_tables() {
    log_info "清空数据库表数据..."
    
    # 检查服务是否运行
    if ! $DOCKER_COMPOSE ps | grep -q "task-service.*Up"; then
        log_info "启动数据库服务..."
        $DOCKER_COMPOSE up -d postgres
        sleep 3
    fi
    
    # 执行清空脚本
    $DOCKER_COMPOSE exec -T postgres psql -U taskmanager -d taskmanager << 'EOF'
-- 禁用外键约束检查
SET session_replication_role = 'replica';

-- 清空所有表
truncate table task_logs, tasks, agents, projects, agent_channels, idempotency_keys restart identity cascade;

-- 重新启用外键约束检查
SET session_replication_role = 'origin';

-- 验证
SELECT 'tasks' as table_name, count(*) as count FROM tasks
UNION ALL
SELECT 'agents', count(*) FROM agents
UNION ALL
SELECT 'projects', count(*) FROM projects
UNION ALL
SELECT 'task_logs', count(*) FROM task_logs;
EOF
    
    log_success "表数据已清空"
}

# 显示帮助信息
show_help() {
    cat << EOF
用法: ./scripts/dev-clean.sh [选项]

选项:
    --all       清空所有数据（包括 Docker 卷）
    --keep-vol  保留 Docker 卷，只清空表数据
    --confirm   跳过确认提示
    --help      显示帮助信息

示例:
    ./scripts/dev-clean.sh --all        # 完全清空（包括卷）
    ./scripts/dev-clean.sh --keep-vol   # 只清空表数据
    ./scripts/dev-clean.sh --all --confirm  # 跳过确认直接清空
EOF
}

# 主函数
main() {
    local all=false
    local keep_vol=false
    local skip_confirm=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --all)
                all=true
                shift
                ;;
            --keep-vol)
                keep_vol=true
                shift
                ;;
            --confirm)
                skip_confirm=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 默认行为：显示帮助
    if [ "$all" = false ] && [ "$keep_vol" = false ]; then
        show_help
        exit 0
    fi
    
    # 确认提示
    if [ "$skip_confirm" = false ]; then
        if [ "$all" = true ]; then
            confirm "⚠️  这将删除所有容器、网络和卷，数据将无法恢复！"
        else
            confirm "⚠️  这将清空所有表数据，但保留数据库结构。"
        fi
    fi
    
    # 执行清理
    if [ "$all" = true ]; then
        stop_services
        clean_all
    else
        clean_tables
    fi
    
    log_success "清理完成！"
}

main "$@"
