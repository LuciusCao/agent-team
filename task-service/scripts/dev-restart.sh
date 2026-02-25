#!/bin/bash
#
# dev-restart.sh - 重启开发服务
#
# 用法: ./scripts/dev-restart.sh [选项]
#   --clean     重启前清空数据
#   --logs      重启后查看日志
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 主函数
main() {
    local clean=false
    local logs=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --clean)
                clean=true
                shift
                ;;
            --logs)
                logs=true
                shift
                ;;
            *)
                echo "未知选项: $1"
                exit 1
                ;;
        esac
    done
    
    log_info "重启开发环境..."
    
    # 停止服务
    log_info "停止服务..."
    docker-compose down
    
    # 如果需要清空数据
    if [ "$clean" = true ]; then
        log_info "清空数据..."
        "$SCRIPT_DIR/dev-clean.sh" --all --confirm
    fi
    
    # 启动服务
    if [ "$logs" = true ]; then
        "$SCRIPT_DIR/dev-start.sh" --logs
    else
        "$SCRIPT_DIR/dev-start.sh"
    fi
    
    log_success "重启完成！"
}

main "$@"
