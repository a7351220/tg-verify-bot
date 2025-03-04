import logging
import os
import asyncio
import random
import io
from datetime import datetime
from collections import deque, defaultdict
from time import time
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler, ConversationHandler
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

# 定義對話狀態
TYPING_CAPTCHA = 1
TYPING_INVITE_CODE = 2

# 存儲待審核用戶
pending_users = {}

# 存儲有效的邀請碼
valid_invite_codes = set()

# 存儲驗證碼
captcha_codes = {}

# 添加用戶嘗試次數限制
user_attempts = defaultdict(int)
attempt_timestamps = defaultdict(float)
MAX_ATTEMPTS = 3
ATTEMPT_RESET_TIME = 3600  # 1小時

# 添加請求頻率限制
user_requests = defaultdict(lambda: deque(maxlen=MAX_REQUESTS))
REQUEST_WINDOW = 60  # 60秒
MAX_REQUESTS = 5  # 每個時間窗口最大請求數

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def check_rate_limit(user_id: int) -> bool:
    current_time = time()
    user_requests[user_id].append(current_time)
    
    if len(user_requests[user_id]) < MAX_REQUESTS:
        return True
    
    # 檢查最早的請求是否在時間窗口外
    oldest_request = user_requests[user_id][0]
    return (current_time - oldest_request) > REQUEST_WINDOW

async def check_attempts(user_id: int) -> tuple[bool, str]:
    current_time = time()
    
    # 檢查是否需要重置嘗試次數
    if current_time - attempt_timestamps[user_id] > ATTEMPT_RESET_TIME:
        user_attempts[user_id] = 0
        attempt_timestamps[user_id] = current_time
    
    if user_attempts[user_id] >= MAX_ATTEMPTS:
        remaining_time = int(ATTEMPT_RESET_TIME - (current_time - attempt_timestamps[user_id]))
        return False, f"❌ 您已超過最大嘗試次數，請在 {remaining_time//60} 分鐘後再試"
    
    return True, ""

async def generate_captcha():
    # 生成 4 位數字驗證碼
    code = ''.join(random.choices('0123456789', k=4))
    
    # 創建圖片
    img = Image.new('RGB', (100, 40), color='white')
    draw = ImageDraw.Draw(img)
    
    # 添加干擾線
    for i in range(5):
        x1 = random.randint(0, 100)
        y1 = random.randint(0, 40)
        x2 = random.randint(0, 100)
        y2 = random.randint(0, 40)
        draw.line([(x1, y1), (x2, y2)], fill='gray')
    
    # 寫入數字
    draw.text((20, 10), code, fill='black')
    
    # 轉換為 bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return code, img_byte_arr

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
    user = query.from_user
    await query.answer()
    
    # 檢查請求頻率
    if not await check_rate_limit(user.id):
        await query.edit_message_text("❌ 請求過於頻繁，請稍後再試")
        return ConversationHandler.END
    
    # 檢查嘗試次數
    can_attempt, message = await check_attempts(user.id)
    if not can_attempt:
        await query.edit_message_text(message)
        return ConversationHandler.END
    
    # 生成驗證碼
    code, img_bytes = await generate_captcha()
    captcha_codes[user.id] = code
    
    # 發送驗證碼圖片
    await context.bot.send_photo(
        chat_id=user.id,
        photo=img_bytes,
        caption="請先輸入圖片中的驗證碼："
    )
    
    return TYPING_CAPTCHA

async def handle_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    captcha_input = update.message.text
    
    # 驗證碼檢查
    if user.id not in captcha_codes or captcha_input != captcha_codes[user.id]:
        user_attempts[user.id] += 1
        del captcha_codes[user.id]  # 清除驗證碼
        
        # 檢查是否達到最大嘗試次數
        can_attempt, message = await check_attempts(user.id)
        if not can_attempt:
            await update.message.reply_text(message)
            return ConversationHandler.END
        
        # 創建開始按鈕和幫助按鈕
        keyboard = [
            [InlineKeyboardButton("🎫 開始驗證", callback_data="start_verify")],
            [InlineKeyboardButton("❓ 查看指令說明", callback_data="show_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 發送錯誤消息並返回開始畫面
        await update.message.reply_text(
            "❌ 驗證碼錯誤，請重新開始\n\n"
            "🔹 本群組需要驗證才能加入\n"
            "🔹 請準備好您的邀請碼\n"
            "🔹 完成驗證後會收到群組邀請連結\n\n"
            "準備好了嗎？點擊下方按鈕開始驗證！",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    # 清除驗證碼
    del captcha_codes[user.id]
    
    # 要求輸入邀請碼
    await update.message.reply_text("請輸入您的邀請碼：")
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
            TYPING_CAPTCHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha)],
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