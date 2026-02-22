#!/bin/bash

# ZeroClaw Agent 启动脚本

AGENT=$1

if [ -z "$AGENT" ]; then
    echo "🚀 启动所有 Agent..."
    docker compose -f agents/researcher/docker-compose.yml --env-file agents/researcher/.env up -d
    docker compose -f agents/copy-writer/docker-compose.yml --env-file agents/copy-writer/.env up -d
    docker compose -f agents/video-master/docker-compose.yml --env-file agents/video-master/.env up -d
    echo ""
    echo "✅ 全部启动完成"
    docker ps --filter "name=zeroclaw-"
else
    echo "🚀 启动 $AGENT ..."
    docker compose -f agents/${AGENT}/docker-compose.yml --env-file agents/${AGENT}/.env up -d
    echo "✅ $AGENT 启动完成"
fi
