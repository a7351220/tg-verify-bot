# Telegram 群組驗證機器人

一個用於管理 Telegram 群組成員驗證的機器人。新成員需要提供邀請碼才能加入群組。

## 功能特點

- 友好的用戶界面
- 引導式驗證流程
- 管理員一鍵審核
- 自動生成一次性邀請連結
- 完整的錯誤處理

## 安裝

1. 克隆倉庫：
```bash
git clone [your-repo-url]
cd tg-verify-bot
```

2. 安裝依賴：
```bash
pip install -r requirements.txt
```

3. 配置環境變量：
   - 複製 `.env.example` 為 `.env`
   - 填入以下信息：
     - BOT_TOKEN：從 @BotFather 獲取的機器人 token
     - GROUP_ID：要管理的群組 ID
     - ADMIN_ID：管理員的 Telegram ID

## 使用方法

1. 運行機器人：
```bash
python bot.py
```

2. 在 Telegram 中：
   - 用戶發送 /start 開始驗證
   - 按照提示輸入邀請碼
   - 等待管理員審核
   - 審核通過後自動收到群組邀請連結

## 管理員功能

- 接收新的驗證請求通知
- 一鍵通過/拒絕驗證
- 自動生成一次性邀請連結

## 授權

MIT License 