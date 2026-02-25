#!/bin/bash
#
# dev-seed.sh - 生成开发测试数据
#
# 用法: ./scripts/dev-seed.sh [选项]
#   --projects N    生成 N 个项目（默认 3）
#   --tasks N       每个项目生成 N 个任务（默认 5）
#   --agents N      生成 N 个 Agent（默认 3）
#   --clean         先清空现有数据
#   -h, --help      显示帮助
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

# 配置
NUM_PROJECTS=3
NUM_TASKS_PER_PROJECT=5
NUM_AGENTS=3
API_BASE="http://localhost:8080"

# 检查服务
check_service() {
    if ! curl -s "$API_BASE/health" > /dev/null 2>&1; then
        log_warn "服务未运行，尝试启动..."
        "$SCRIPT_DIR/dev-start.sh"
        sleep 5
    fi
}

# 生成项目
seed_projects() {
    log_info "生成 $NUM_PROJECTS 个项目..."
    
    for i in $(seq 1 $NUM_PROJECTS); do
        curl -s -X POST "$API_BASE/v1/projects" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${API_KEY:-}" \
            -d "{
                \"name\": \"开发项目 $i\",
                \"description\": \"这是用于开发的测试项目 $i\"
            }" > /dev/null
        echo -n "."
    done
    echo
    log_success "项目生成完成"
}

# 生成 Agent
seed_agents() {
    log_info "生成 $NUM_AGENTS 个 Agent..."
    
    local roles=("research" "developer" "designer")
    local skills_list=(
        '["python", "data-analysis"]'
        '["javascript", "react", "nodejs"]'
        '["ui-design", "figma"]'
    )
    
    for i in $(seq 1 $NUM_AGENTS); do
        local role_idx=$(( (i-1) % 3 ))
        curl -s -X POST "$API_BASE/v1/agents/register" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${API_KEY:-}" \
            -d "{
                \"name\": \"dev-agent-$i\",
                \"role\": \"${roles[$role_idx]}\",
                \"skills\": ${skills_list[$role_idx]}
            }" > /dev/null
        echo -n "."
    done
    echo
    log_success "Agent 生成完成"
}

# 生成任务
seed_tasks() {
    log_info "生成任务..."
    
    # 获取所有项目
    local projects=$(curl -s "$API_BASE/v1/projects" | python3 -c "import sys,json; print(' '.join([str(p['id']) for p in json.load(sys.stdin)]))")
    
    local task_types=("research" "development" "design" "testing")
    local priorities=(5 7 9)
    
    for project_id in $projects; do
        for i in $(seq 1 $NUM_TASKS_PER_PROJECT); do
            local type_idx=$(( (i-1) % 4 ))
            local priority_idx=$(( (i-1) % 3 ))
            
            curl -s -X POST "$API_BASE/v1/tasks" \
                -H "Content-Type: application/json" \
                -H "X-API-Key: ${API_KEY:-}" \
                -d "{
                    \"project_id\": $project_id,
                    \"title\": \"任务 $i - 项目 $project_id\",
                    \"description\": \"这是测试任务 $i\",
                    \"task_type\": \"${task_types[$type_idx]}\",
                    \"priority\": ${priorities[$priority_idx]},
                    \"task_tags\": [\"${task_types[$type_idx]}\"]
                }" > /dev/null
            echo -n "."
        done
    done
    echo
    log_success "任务生成完成"
}

# 显示帮助
show_help() {
    cat << 'EOF'
用法: ./scripts/dev-seed.sh [选项]

选项:
    --projects N    生成 N 个项目（默认 3）
    --tasks N       每个项目生成 N 个任务（默认 5）
    --agents N      生成 N 个 Agent（默认 3）
    --clean         先清空现有数据
    -h, --help      显示帮助

示例:
    ./scripts/dev-seed.sh              # 生成默认数据
    ./scripts/dev-seed.sh --clean      # 清空后生成
    ./scripts/dev-seed.sh --projects 5 --tasks 10  # 生成更多数据
EOF
}

# 主函数
main() {
    local clean=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --projects)
                NUM_PROJECTS="$2"
                shift 2
                ;;
            --tasks)
                NUM_TASKS_PER_PROJECT="$2"
                shift 2
                ;;
            --agents)
                NUM_AGENTS="$2"
                shift 2
                ;;
            --clean)
                clean=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                echo "未知选项: $1"
                exit 1
                ;;
        esac
    done
    
    if [ "$clean" = true ]; then
        log_warn "清空现有数据..."
        "$SCRIPT_DIR/dev-clean.sh" --keep-vol --confirm
    fi
    
    check_service
    
    log_info "开始生成测试数据..."
    seed_projects
    seed_agents
    seed_tasks
    
    log_success "测试数据生成完成！"
    echo ""
    echo "生成的数据："
    echo "  - 项目: $NUM_PROJECTS 个"
    echo "  - Agent: $NUM_AGENTS 个"
    echo "  - 任务: $(($NUM_PROJECTS * $NUM_TASKS_PER_PROJECT)) 个"
}

main "$@"
