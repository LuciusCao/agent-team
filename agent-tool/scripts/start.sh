#!/bin/bash

# ZeroClaw Agent 启动脚本

AGENT=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_TOOL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$AGENT_TOOL_DIR")"

if [ -z "$AGENT" ]; then
    echo "🚀 启动所有 Agent..."
    docker compose -f "$PROJECT_DIR/agents/researcher/docker-compose.yml" --env-file "$PROJECT_DIR/agents/researcher/.env" up -d
    docker compose -f "$PROJECT_DIR/agents/copy-writer/docker-compose.yml" --env-file "$PROJECT_DIR/agents/copy-writer/.env" up -d
    docker compose -f "$PROJECT_DIR/agents/video-master/docker-compose.yml" --env-file "$PROJECT_DIR/agents/video-master/.env" up -d
    echo ""
    echo "✅ 全部启动完成"
    docker ps --filter "name=zeroclaw-"
else
    echo "🚀 启动 $AGENT ..."
    docker compose -f "$PROJECT_DIR/agents/${AGENT}/docker-compose.yml" --env-file "$PROJECT_DIR/agents/${AGENT}/.env" up -d
    echo "✅ $AGENT 启动完成"
fi
