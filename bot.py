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

# 存儲待審核用戶
pending_users = {}

# 存儲有效的邀請碼
valid_invite_codes = set()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    
    # 創建開始按鈕和幫助按鈕
    keyboard = [
        [InlineKeyboardButton("🎫 開始驗證", callback_data="start_verify")],
        [InlineKeyboardButton("❓ 查看指令說明", callback_data="show_help")]
    ]
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

async def add_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 檢查是否是管理員
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.message.reply_text("❌ 只有管理員可以使用此命令")
        return
    
    # 檢查是否有提供邀請碼
    if not context.args:
        await update.message.reply_text(
            "❌ 請提供邀請碼\n"
            "格式：/add_codes code1 code2 code3"
        )
        return
    
    # 添加邀請碼
    added_codes = []
    for code in context.args:
        if code not in valid_invite_codes:
            valid_invite_codes.add(code)
            added_codes.append(code)
    
    # 回覆結果
    if added_codes:
        await update.message.reply_text(
            f"✅ 已添加 {len(added_codes)} 個邀請碼：\n" + 
            "\n".join(f"🎫 {code}" for code in added_codes)
        )
    else:
        await update.message.reply_text("❌ 沒有新的邀請碼被添加")

async def list_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 檢查是否是管理員
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.message.reply_text("❌ 只有管理員可以使用此命令")
        return
    
    # 顯示所有有效的邀請碼
    if not valid_invite_codes:
        await update.message.reply_text("📝 目前沒有可用的邀請碼")
        return
    
    codes_list = "📋 可用的邀請碼列表：\n\n" + "\n".join(f"🎫 {code}" for code in valid_invite_codes)
    await update.message.reply_text(codes_list)

async def handle_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    invite_code = update.message.text
    user = update.effective_user
    
    # 檢查是否是有效的邀請碼
    if invite_code in valid_invite_codes:
        try:
            # 生成邀請連結
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=os.getenv('GROUP_ID'),
                member_limit=1
            )
            
            # 發送邀請連結給用戶
            await update.message.reply_text(
                "🎉 邀請碼驗證通過！\n\n"
                f"🔗 這是您的群組邀請連結：\n{invite_link.invite_link}\n\n"
                "⚠️ 請注意：此連結僅能使用一次"
            )
            
            # 移除已使用的邀請碼
            valid_invite_codes.remove(invite_code)
            
            # 記錄到日誌
            logging.info(f"User {user.username} (ID: {user.id}) used invite code: {invite_code}")
            
            return ConversationHandler.END
            
        except Exception as e:
            logging.error(f"Error creating invite link: {e}")
            # 如果出錯，保留邀請碼
            await update.message.reply_text(
                "❌ 抱歉，生成邀請連結時出現錯誤，請稍後再試或聯繫管理員"
            )
            return ConversationHandler.END
    
    # 如果不是有效邀請碼，走原來的審核流程
    # 存儲用戶資訊
    pending_users[user.id] = {
        'username': user.username,
        'first_name': user.first_name,
        'invite_code': invite_code,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
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

async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 檢查是否是管理員
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.message.reply_text("❌ 只有管理員可以使用此命令")
        return
    
    if not pending_users:
        await update.message.reply_text("📝 目前沒有待審核的用戶")
        return
    
    # 生成待審核用戶列表
    message = "📋 待審核用戶列表：\n\n"
    for user_id, info in pending_users.items():
        message += (
            f"👤 用戶: @{info['username']}\n"
            f"📌 ID: {user_id}\n"
            f"👋 名稱: {info['first_name']}\n"
            f"🎫 邀請碼: {info['invite_code']}\n"
            f"⏰ 時間: {info['time']}\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
        )
    
    # 添加導出邀請碼按鈕
    keyboard = [[InlineKeyboardButton("📥 導出邀請碼列表", callback_data="export_codes")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "show_help":
        is_admin = str(query.from_user.id) == os.getenv('ADMIN_ID')
        
        help_text = (
            "📚 可用的指令列表：\n\n"
            "一般用戶指令：\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "/start - 開始使用機器人\n"
            "/help - 顯示此幫助訊息\n"
            "/cancel - 取消當前操作\n\n"
        )
        
        if is_admin:
            help_text += (
                "管理員指令：\n"
                "➖➖➖➖➖➖➖➖➖➖\n"
                "/pending - 查看待審核的用戶列表\n"
                "/approve_codes - 批量批准指定邀請碼的用戶\n"
                "格式：/approve_codes code1 code2 code3\n\n"
                "💡 提示：\n"
                "• 在待審核列表中可以導出純邀請碼列表\n"
                "• 可以對單個用戶進行審核或拒絕\n"
                "• 也可以使用 /approve_codes 批量處理"
            )
        
        # 添加返回按鈕
        keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="back_to_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)
        return
    
    if query.data == "back_to_start":
        # 返回開始界面
        keyboard = [
            [InlineKeyboardButton("🎫 開始驗證", callback_data="start_verify")],
            [InlineKeyboardButton("❓ 查看指令說明", callback_data="show_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_message = (
            "👋 歡迎來到驗證機器人！\n\n"
            "🔹 本群組需要驗證才能加入\n"
            "🔹 請準備好您的邀請碼\n"
            "🔹 完成驗證後會收到群組邀請連結\n\n"
            "準備好了嗎？點擊下方按鈕開始驗證！"
        )
        
        await query.edit_message_text(welcome_message, reply_markup=reply_markup)
        return
    
    if query.data == "export_codes":
        if not pending_users:
            await query.edit_message_text("📝 目前沒有待審核的用戶")
            return
        
        # 生成純邀請碼列表
        codes_list = "📥 邀請碼列表：\n\n"
        for info in pending_users.values():
            codes_list += f"🎫 {info['invite_code']}\n"
        
        await query.message.reply_text(codes_list)
        return
    
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
        
        # 從待審核列表中移除
        if user_id in pending_users:
            del pending_users[user_id]
    
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
        
        # 從待審核列表中移除
        if user_id in pending_users:
            del pending_users[user_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ 驗證已取消。如需重新驗證，請發送 /start",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def approve_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 檢查是否是管理員
    if str(update.effective_user.id) != os.getenv('ADMIN_ID'):
        await update.message.reply_text("❌ 只有管理員可以使用此命令")
        return
    
    # 檢查是否有提供邀請碼
    if not context.args:
        await update.message.reply_text(
            "❌ 請提供要批准的邀請碼\n"
            "格式：/approve_codes code1 code2 code3"
        )
        return
    
    valid_codes = set(context.args)
    approved_count = 0
    not_found = []
    
    # 找出所有匹配邀請碼的用戶
    for user_id, info in list(pending_users.items()):  # 使用 list() 因為我們會修改字典
        if info['invite_code'] in valid_codes:
            try:
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
                
                # 從待審核列表中移除
                del pending_users[user_id]
                approved_count += 1
                
                # 記錄到日誌
                logging.info(f"Approved user {info['username']} (ID: {user_id}) with invite code: {info['invite_code']}")
                
            except Exception as e:
                logging.error(f"Error approving user {user_id}: {e}")
        
    # 檢查哪些邀請碼沒有找到對應用戶
    for code in valid_codes:
        if not any(info['invite_code'] == code for info in pending_users.values()):
            not_found.append(code)
    
    # 生成結果消息
    result_message = f"✅ 已批准 {approved_count} 個用戶\n"
    if not_found:
        result_message += f"\n❌ 這些邀請碼沒有找到對應的待審核用戶：\n" + "\n".join(f"🎫 {code}" for code in not_found)
    
    await update.message.reply_text(result_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = str(update.effective_user.id) == os.getenv('ADMIN_ID')
    
    help_text = (
        "📚 可用的指令列表：\n\n"
        "一般用戶指令：\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "/start - 開始使用機器人\n"
        "/help - 顯示此幫助訊息\n"
        "/cancel - 取消當前操作\n\n"
    )
    
    if is_admin:
        help_text += (
            "管理員指令：\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "/pending - 查看待審核的用戶列表\n"
            "/approve_codes - 批量批准指定邀請碼的用戶\n"
            "格式：/approve_codes code1 code2 code3\n\n"
            "💡 提示：\n"
            "• 在待審核列表中可以導出純邀請碼列表\n"
            "• 可以對單個用戶進行審核或拒絕\n"
            "• 也可以使用 /approve_codes 批量處理"
        )
    
    await update.message.reply_text(help_text)

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
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('pending', list_pending))
    application.add_handler(CommandHandler('add_codes', add_codes))
    application.add_handler(CommandHandler('list_codes', list_codes))
    application.add_handler(CommandHandler('approve_codes', approve_codes))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    # Run the bot
    print("Starting bot...")
    application.run_polling() 