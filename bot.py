import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler, ConversationHandler
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

# 定義對話狀態
TYPING_INVITE_CODE = 1

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    
    # 創建開始按鈕
    keyboard = [[InlineKeyboardButton("🎫 開始驗證", callback_data="start_verify")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 發送歡迎消息
    welcome_message = (
        "👋 歡迎來到驗證機器人！\n\n"
        "🔹 本群組需要驗證才能加入\n"
        "🔹 請準備好您的邀請碼\n"
        "🔹 完成驗證後會收到群組邀請連結\n\n"
        "準備好了嗎？點擊下方按鈕開始驗證！"
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup
    )

async def start_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # 要求用戶輸入邀請碼
    await query.edit_message_text(
        "請輸入您的邀請碼：",
        reply_markup=None
    )
    return TYPING_INVITE_CODE

async def handle_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    invite_code = update.message.text
    user = update.effective_user
    
    # 創建審核按鈕
    keyboard = [
        [
            InlineKeyboardButton("✅ 通過", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ 拒絕", callback_data=f"reject_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 發送驗證請求給管理員
    admin_message = (
        f"📝 新的驗證請求\n\n"
        f"👤 用戶: @{user.username}\n"
        f"📌 ID: {user.id}\n"
        f"👋 名稱: {user.first_name}\n"
        f"🎫 邀請碼: {invite_code}\n"
        f"⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    await context.bot.send_message(
        chat_id=os.getenv('ADMIN_ID'),
        text=admin_message,
        reply_markup=reply_markup
    )
    
    # 通知用戶
    await update.message.reply_text(
        "✅ 您的驗證請求已提交！\n"
        "⏳ 請耐心等待管理員審核，審核結果會通過機器人通知您。"
    )
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    if action == "approve":
        # 生成邀請連結
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=os.getenv('GROUP_ID'),
            member_limit=1
        )
        
        # 發送邀請連結給用戶
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 恭喜！您的驗證請求已通過！\n\n"
                f"🔗 這是您的群組邀請連結：\n{invite_link.invite_link}\n\n"
                "⚠️ 請注意：此連結僅能使用一次"
            )
        )
        
        # 更新管理員消息
        await query.edit_message_text(
            text=f"{query.message.text}\n\n✅ 已通過 - 管理員已審核"
        )
    
    elif action == "reject":
        # 通知用戶
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ 很抱歉，您的驗證請求未通過審核。"
        )
        
        # 更新管理員消息
        await query.edit_message_text(
            text=f"{query.message.text}\n\n❌ 已拒絕 - 管理員已審核"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ 驗證已取消。如需重新驗證，請發送 /start",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Error occurred: {context.error}")

if __name__ == '__main__':
    # Initialize application
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # 設置對話處理
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_verification, pattern='^start_verify$')],
        states={
            TYPING_INVITE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invite_code)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    # Run the bot
    print("Starting bot...")
    application.run_polling() 