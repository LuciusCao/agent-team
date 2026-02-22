#!/bin/bash

# ZeroClaw Agent 停止脚本

AGENT=$1

if [ -z "$AGENT" ]; then
    echo "🛑 停止所有 Agent..."
    docker compose -f agents/researcher/docker-compose.yml --env-file agents/researcher/.env down
    docker compose -f agents/copy-writer/docker-compose.yml --env-file agents/copy-writer/.env down
    docker compose -f agents/video-master/docker-compose.yml --env-file agents/video-master/.env down
    echo "✅ 全部停止"
else
    echo "🛑 停止 $AGENT ..."
    docker compose -f agents/${AGENT}/docker-compose.yml --env-file agents/${AGENT}/.env down
    echo "✅ $AGENT 已停止"
fi
