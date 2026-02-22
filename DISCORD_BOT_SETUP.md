# Discord Bot 创建指南 (3 个 Bot)

## 概述

本项目需要创建 **3 个 Discord Bot**，分别对应 3 个 ZeroClaw Agent：

| Bot 名称 | 对应 Agent | 职责 |
|----------|------------|------|
| zeroclaw-researcher | Researcher | 调研、选题 |
| zeroclaw-copy-writer | Copy Writer | 文案创作 |
| zeroclaw-video-master | Video Master | 视频创作 |

## 创建步骤

### 步骤 1: 创建应用

1. 访问 https://discord.com/developers/applications
2. 点击 **New Application**
3. 创建 **3 个应用**:
   - `zeroclaw-researcher`
   - `zeroclaw-copy-writer`
   - `zeroclaw-video-master`

### 步骤 2: 添加 Bot

对于每个应用:

1. 在左侧菜单点击 **Bot**
2. 点击 **Add Bot**
3. 点击 **Yes, do it!**
4. **重命名** Bot (可选)

### 步骤 3: 获取 Token

对于每个 Bot:

1. 点击 **Reset Token**（如果需要）
2. 点击 **Copy** 复制 Token
3. 将 Token 填入 `.env`:

```env
RESEARCHER_DISCORD_BOT_TOKEN=xxx
COPY_WRITER_DISCORD_BOT_TOKEN=xxx
VIDEO_MASTER_DISCORD_BOT_TOKEN=xxx
```

⚠️ **注意**: Token 只显示一次，请妥善保存！

### 步骤 4: 开启 Message Content Intent

对于每个 Bot:

1. 在 Bot 页面，滚动到 **Privileged Gateways**
2. 找到 **Message Content Intent**
3. 点击 **Enable**
4. 点击 **Save Changes**

### 步骤 5: 配置权限

对于每个 Bot:

1. 左侧菜单 **OAuth2** → **URL Generator**
2. **Scopes** 勾选: `bot`
3. **Bot Permissions** 勾选:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Manage Messages
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Use External Emojis
   - ✅ Add Reactions
4. 复制生成的 **Invite URL**

### 步骤 6: 邀请 Bot

用 3 个不同的 Invite URL，把 3 个 Bot 都邀请到同一个服务器/频道。

### 步骤 7: 获取服务器和频道 ID

1. Discord 设置 → Advanced → Developer Mode → 开启
2. 右键服务器 → Copy ID → 填入 `DISCORD_GUILD_ID`
3. 右键频道 → Copy ID → 填入 `DISCORD_CHANNEL_ID`

## .env 配置示例

```env
# 3 个 Bot Token
RESEARCHER_DISCORD_BOT_TOKEN=Bot1_token_here
COPY_WRITER_DISCORD_BOT_TOKEN=Bot2_token_here
VIDEO_MASTER_DISCORD_BOT_TOKEN=Bot3_token_here

# 服务器/频道
DISCORD_GUILD_ID=123456789012345678
DISCORD_CHANNEL_ID=123456789012345678

# LLM Keys
RESEARCHER_API_KEY=openrouter_xxx
COPY_WRITER_API_KEY=minimax_xxx
VIDEO_MASTER_API_KEY=minimax_xxx
```

## 验证

3 个 Bot 都加入服务器后，应该都能在成员列表中看到。
