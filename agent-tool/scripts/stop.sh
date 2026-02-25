#!/bin/bash

# ZeroClaw Agent 停止脚本

AGENT=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_TOOL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$AGENT_TOOL_DIR")"

if [ -z "$AGENT" ]; then
    echo "🛑 停止所有 Agent..."
    docker compose -f "$PROJECT_DIR/agents/researcher/docker-compose.yml" --env-file "$PROJECT_DIR/agents/researcher/.env" down
    docker compose -f "$PROJECT_DIR/agents/copy-writer/docker-compose.yml" --env-file "$PROJECT_DIR/agents/copy-writer/.env" down
    docker compose -f "$PROJECT_DIR/agents/video-master/docker-compose.yml" --env-file "$PROJECT_DIR/agents/video-master/.env" down
    echo "✅ 全部停止"
else
    echo "🛑 停止 $AGENT ..."
    docker compose -f "$PROJECT_DIR/agents/${AGENT}/docker-compose.yml" --env-file "$PROJECT_DIR/agents/${AGENT}/.env" down
    echo "✅ $AGENT 已停止"
fi
