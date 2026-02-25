#!/bin/bash

# 生成 Agent 配置
# 用法: ./config.sh <agent-name>

AGENT_NAME=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_TOOL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$AGENT_TOOL_DIR")"

if [ -z "$AGENT_NAME" ]; then
    echo "用法: ./config.sh <agent-name>"
    exit 1
fi

AGENT_DIR="$PROJECT_DIR/agents/${AGENT_NAME}"

if [ ! -d "$AGENT_DIR" ]; then
    echo "❌ 目录不存在: $AGENT_DIR"
    exit 1
fi

# 加载 .env
if [ -f "$AGENT_DIR/.env" ]; then
    source "$AGENT_DIR/.env"
elif [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
else
    echo "❌ 未找到 .env 文件"
    exit 1
fi

echo "=== 配置 ${AGENT_NAME} ==="

# 创建 workspace 目录
mkdir -p "$AGENT_DIR/workspace"

# 复制配置文件
cp "$AGENT_TOOL_DIR/templates/config.example.toml" "$AGENT_DIR/config.toml"

# 替换变量
sed -i '' "s|^bot_token = \"\"|bot_token = \"${DISCORD_BOT_TOKEN}\"|" "$AGENT_DIR/config.toml"
[ -n "$DISCORD_GUILD_ID" ] && sed -i '' "s|^guild_id = \"\"|guild_id = \"${DISCORD_GUILD_ID}\"|" "$AGENT_DIR/config.toml"
[ -n "$API_KEY" ] && sed -i '' "s|^api_key = \"\"|api_key = \"${API_KEY}\"|" "$AGENT_DIR/config.toml"
[ -n "$PROVIDER" ] && sed -i '' "s|^default_provider = \"kimi-code\"|default_provider = \"${PROVIDER}\"|" "$AGENT_DIR/config.toml"
[ -n "$MODEL" ] && sed -i '' "s|^default_model = \"kimi-k2.5\"|default_model = \"${MODEL}\"|" "$AGENT_DIR/config.toml"

# 复制 identity 模板（不覆盖已有）
[ -f "$AGENT_TOOL_DIR/templates/SOUL.example.md" ] && cp -n "$AGENT_TOOL_DIR/templates/SOUL.example.md" "$AGENT_DIR/workspace/SOUL.md" 2>/dev/null || true
[ -f "$AGENT_TOOL_DIR/templates/AGENTS.example.md" ] && cp -n "$AGENT_TOOL_DIR/templates/AGENTS.example.md" "$AGENT_DIR/workspace/AGENTS.md" 2>/dev/null || true

echo "✅ 完成: $AGENT_DIR/config.toml"
echo "✅ workspace 目录已创建"
