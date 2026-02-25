#!/bin/bash
#
# dev.sh - 开发工具主入口
#
# 用法: ./scripts/dev.sh <命令> [选项]
#
# 命令:
#   start       启动开发环境
#   stop        停止开发环境
#   restart     重启开发环境
#   clean       清空开发数据
#   logs        查看日志
#   test        运行测试
#   seed        生成测试数据
#   status      查看服务状态
#   help        显示帮助
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检测 docker compose 命令
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}错误: 未找到 docker compose 命令${NC}"
    exit 1
fi

# 颜色定义
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

show_help() {
    cat << EOF
开发工具集 - 快速管理开发环境

用法: ./scripts/dev.sh <命令> [选项]

命令:
    start [选项]     启动开发环境
                     --fresh     清空数据库后启动
                     --logs      启动并查看日志

    stop             停止开发环境

    restart [选项]   重启开发环境
                     --clean     重启前清空数据
                     --logs      重启后查看日志

    clean [选项]     清空开发数据
                     --all       清空所有数据（包括卷）
                     --keep-vol  只清空表数据

    logs [选项]      查看日志
                     -f          持续跟踪
                     -n N        显示最后 N 行
                     [服务名]    指定服务（默认 task-service）

    test [选项]      运行测试
                     -v          详细输出
                     -k KEYWORD  匹配关键字
                     --cov       覆盖率报告
                     --watch     监视模式

    seed [选项]      生成测试数据
                     --clean     先清空数据
                     --projects N
                     --tasks N
                     --agents N

    status           查看服务状态

    help             显示此帮助

示例:
    ./scripts/dev.sh start              # 正常启动
    ./scripts/dev.sh start --fresh      # 干净启动
    ./scripts/dev.sh clean --all        # 完全清空
    ./scripts/dev.sh logs -f            # 跟踪日志
    ./scripts/dev.sh test --cov         # 覆盖率测试
    ./scripts/dev.sh seed --clean       # 清空后生成数据

EOF
}

# 检查脚本是否存在
check_script() {
    local script="$1"
    if [ ! -f "$SCRIPT_DIR/$script" ]; then
        echo -e "${RED}错误: 脚本 $script 不存在${NC}"
        exit 1
    fi
    chmod +x "$SCRIPT_DIR/$script"
}

# 显示状态
show_status() {
    echo -e "${BLUE}服务状态:${NC}"
    $DOCKER_COMPOSE ps
    
    echo ""
    echo -e "${BLUE}健康检查:${NC}"
    if curl -s http://localhost:8080/health 2>/dev/null | python3 -m json.tool 2>/dev/null; then
        echo ""
        echo -e "${GREEN}✓ 服务运行正常${NC}"
    else
        echo -e "${RED}✗ 服务未响应${NC}"
    fi
}

# 主命令处理
case "${1:-help}" in
    start)
        shift
        check_script "dev-start.sh"
        "$SCRIPT_DIR/dev-start.sh" "$@"
        ;;
    stop)
        shift
        echo -e "${BLUE}停止开发环境...${NC}"
        $DOCKER_COMPOSE down
        echo -e "${GREEN}✓ 已停止${NC}"
        ;;
    restart)
        shift
        check_script "dev-restart.sh"
        "$SCRIPT_DIR/dev-restart.sh" "$@"
        ;;
    clean)
        shift
        check_script "dev-clean.sh"
        "$SCRIPT_DIR/dev-clean.sh" "$@"
        ;;
    logs)
        shift
        check_script "dev-logs.sh"
        "$SCRIPT_DIR/dev-logs.sh" "$@"
        ;;
    test)
        shift
        check_script "dev-test.sh"
        "$SCRIPT_DIR/dev-test.sh" "$@"
        ;;
    seed)
        shift
        check_script "dev-seed.sh"
        "$SCRIPT_DIR/dev-seed.sh" "$@"
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}未知命令: $1${NC}"
        show_help
        exit 1
        ;;
esac
