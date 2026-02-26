#!/bin/bash
#
# dev-test.sh - 运行测试
#
# 用法: ./scripts/dev-test.sh [选项]
#   -v, --verbose   详细输出
#   -k KEYWORD      只运行匹配关键字的测试
#   --cov           生成覆盖率报告
#   --watch         监视文件变化自动运行
#   -h, --help      显示帮助
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
NC='\033[0m'

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

# 显示帮助
show_help() {
    cat << 'EOF'
用法: ./scripts/dev-test.sh [选项]

选项:
    -v, --verbose   详细输出
    -k KEYWORD      只运行匹配关键字的测试
    --cov           生成覆盖率报告
    --watch         监视文件变化自动运行（需要 pytest-watch）
    -h, --help      显示帮助

示例:
    ./scripts/dev-test.sh              # 运行所有测试
    ./scripts/dev-test.sh -v           # 详细输出
    ./scripts/dev-test.sh -k test_create   # 只运行包含 test_create 的测试
    ./scripts/dev-test.sh --cov        # 生成覆盖率报告
EOF
}

# 检查服务是否运行
check_service() {
    if ! curl -s http://localhost:8080/health > /dev/null 2>&1; then
        log_warn "服务未运行，尝试启动..."
        "$SCRIPT_DIR/dev-start.sh"
        sleep 3
    fi
}

# 运行测试
run_tests() {
    local verbose=""
    local keyword=""
    local cov=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                verbose="-v"
                shift
                ;;
            -k)
                keyword="-k $2"
                shift 2
                ;;
            --cov)
                cov="--cov=. --cov-report=term-missing --cov-report=html"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    log_info "运行测试..."
    
    if [ -n "$cov" ]; then
        log_info "覆盖率报告将生成在 htmlcov/ 目录"
    fi
    
    # 使用 uv 运行测试
    if command -v uv > /dev/null 2>&1; then
        log_info "使用 uv 运行测试 ✓"
        uv run pytest tests/ $verbose $keyword $cov --tb=short
    else
        log_warn "uv 未安装，使用 python3 运行测试"
        python3 -m pytest tests/ $verbose $keyword $cov --tb=short
    fi
}

# 监视模式
watch_tests() {
    log_info "监视模式 - 文件变化时自动运行测试"
    log_info "按 Ctrl+C 退出"
    
    if command -v uv > /dev/null 2>&1; then
        log_info "使用 uv 运行 pytest-watch ✓"
        uv run ptw tests/ -- -v --tb=short
    else
        log_warn "uv 未安装，使用 pip 安装 pytest-watch"
        if ! command -v ptw > /dev/null 2>&1; then
            log_info "安装 pytest-watch..."
            pip install pytest-watch
        fi
        ptw tests/ -- -v --tb=short
    fi
}

# 主函数
main() {
    local args=()
    local watch=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            --watch)
                watch=true
                shift
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    
    if [ "$watch" = true ]; then
        watch_tests
    else
        check_service
        run_tests "${args[@]}"
        log_success "测试完成！"
    fi
}

main "$@"
