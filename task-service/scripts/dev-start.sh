#!/bin/bash
#
# dev-start.sh - 快速启动开发环境
#
# 用法: ./scripts/dev-start.sh [选项]
#   --fresh     清空数据库后启动（干净环境）
#   --logs      启动并查看日志
#   --detach    后台启动（默认）
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
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

# 检查 Docker 是否运行
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker 未运行，请先启动 Docker"
        exit 1
    fi
}

# 清空数据库
fresh_start() {
    log_warn "正在清空数据库..."
    docker-compose down -v
    log_success "数据库已清空"
}

# 启动服务
start_services() {
    log_info "启动开发环境..."
    
    # 检查 .env 文件
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在，使用默认配置"
        cp .env.example .env 2>/dev/null || true
    fi
    
    # 构建并启动
    docker-compose up --build -d
    
    log_info "等待服务启动..."
    sleep 3
    
    # 检查服务健康状态
    check_health
}

# 检查服务健康状态
check_health() {
    log_info "检查服务健康状态..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            log_success "服务已启动并运行正常！"
            echo ""
            echo "========================================"
            echo "  服务地址: http://localhost:8080"
            echo "  API 文档: http://localhost:8080/docs"
            echo "  健康检查: http://localhost:8080/health"
            echo "========================================"
            return 0
        fi
        
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    log_error "服务启动超时，请检查日志"
    return 1
}

# 查看日志
show_logs() {
    log_info "查看服务日志（按 Ctrl+C 退出）..."
    docker-compose logs -f task-service
}

# 显示帮助信息
show_help() {
    cat << EOF
用法: ./scripts/dev-start.sh [选项]

选项:
    --fresh     清空数据库后启动（干净环境）
    --logs      启动并查看日志
    --help      显示帮助信息

示例:
    ./scripts/dev-start.sh              # 正常启动
    ./scripts/dev-start.sh --fresh      # 清空数据库后启动
    ./scripts/dev-start.sh --logs       # 启动并查看日志
EOF
}

# 主函数
main() {
    local fresh=false
    local logs=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --fresh)
                fresh=true
                shift
                ;;
            --logs)
                logs=true
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
    
    # 检查 Docker
    check_docker
    
    # 如果需要清空数据库
    if [ "$fresh" = true ]; then
        fresh_start
    fi
    
    # 启动服务
    start_services
    
    # 如果需要查看日志
    if [ "$logs" = true ]; then
        show_logs
    fi
}

main "$@"
