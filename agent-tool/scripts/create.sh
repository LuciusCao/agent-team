#!/bin/bash

# 创建新 Agent 的脚本
# 用法: ./create.sh <agent-name>
# 例: ./create.sh new-agent

AGENT_NAME=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_TOOL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$AGENT_TOOL_DIR")"

if [ -z "$AGENT_NAME" ]; then
    echo "用法: ./create.sh <agent-name>"
    echo "例: ./create.sh new-agent"
    exit 1
fi

# 检查目录是否已存在
if [ -d "$PROJECT_DIR/agents/${AGENT_NAME}" ]; then
    echo "❌ Agent ${AGENT_NAME} 已存在"
    exit 1
fi

echo "🚀 创建 Agent: ${AGENT_NAME}"

# 创建目录
mkdir -p "$PROJECT_DIR/agents/${AGENT_NAME}/workspace"

# 复制 docker-compose 模板
if [ -f "$AGENT_TOOL_DIR/templates/docker-compose.example.yml" ]; then
    cp "$AGENT_TOOL_DIR/templates/docker-compose.example.yml" "$PROJECT_DIR/agents/${AGENT_NAME}/docker-compose.yml"
    
    # 替换容器名
    sed -i '' "s|zeroclaw-[a-z-]*|zeroclaw-${AGENT_NAME}|g" "$PROJECT_DIR/agents/${AGENT_NAME}/docker-compose.yml"
    
    # 替换 volume 名称
    sed -i '' "s|zeroclaw-data|${AGENT_NAME}-data|g" "$PROJECT_DIR/agents/${AGENT_NAME}/docker-compose.yml"
    
    # 替换端口（递增）
    BASE_PORT=43000
    AGENT_COUNT=$(ls -d "$PROJECT_DIR"/agents/*/ 2>/dev/null | wc -l)
    NEW_PORT=$((BASE_PORT + AGENT_COUNT + 1))
    sed -i '' "s|4300[0-9]|${NEW_PORT}|g" "$PROJECT_DIR/agents/${AGENT_NAME}/docker-compose.yml"
fi

# 复制 config 模板
if [ -f "$AGENT_TOOL_DIR/templates/config.example.toml" ]; then
    cp "$AGENT_TOOL_DIR/templates/config.example.toml" "$PROJECT_DIR/agents/${AGENT_NAME}/config.toml"
fi

# 复制 .env 模板
if [ -f "$AGENT_TOOL_DIR/templates/.env.example" ]; then
    cp "$AGENT_TOOL_DIR/templates/.env.example" "$PROJECT_DIR/agents/${AGENT_NAME}/.env"
    # 替换 AGENT_NAME
    sed -i '' "s|AGENT_NAME=agent|AGENT_NAME=${AGENT_NAME}|g" "$PROJECT_DIR/agents/${AGENT_NAME}/.env"
fi

# 复制 identity 模板文件（不覆盖已有）
if [ -f "$AGENT_TOOL_DIR/templates/SOUL.example.md" ]; then
    cp -n "$AGENT_TOOL_DIR/templates/SOUL.example.md" "$PROJECT_DIR/agents/${AGENT_NAME}/workspace/SOUL.md" 2>/dev/null || true
fi

if [ -f "$AGENT_TOOL_DIR/templates/AGENTS.example.md" ]; then
    cp -n "$AGENT_TOOL_DIR/templates/AGENTS.example.md" "$PROJECT_DIR/agents/${AGENT_NAME}/workspace/AGENTS.md" 2>/dev/null || true
fi

echo "✅ Agent ${AGENT_NAME} 创建完成!"
echo ""
echo "下一步:"
echo "  1. 编辑 ./agents/${AGENT_NAME}/.env 填入配置"
echo "  2. 运行 agent config ${AGENT_NAME} 生成配置"
echo "  3. 运行 agent start {AGENT_NAME} 启动"
