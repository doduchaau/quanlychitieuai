import os
import logging
import io
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv

import database as db
from ai_handler import (
    process_message,
    process_voice,
    process_image,
    format_balance,
    format_list,
    format_report,
    format_prediction,
    format_daily_reminder,
    format_money,
    format_wallets,
)
from charts import (
    create_category_chart,
    create_income_expense_chart,
    create_daily_chart,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret_change_me")
PORT = int(os.getenv("PORT", 10000))
REMIND_HOUR = int(os.getenv("REMIND_HOUR", 21))

if not TELEGRAM_TOKEN:
    raise ValueError("Thiếu TELEGRAM_BOT_TOKEN!")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

application = (
    Application.builder()
    .token(TELEGRAM_TOKEN)
    .updater(None)
    .build()
)

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Ho_Chi_Minh"))


# ========== HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Tạo ví mặc định ngay khi /start
    await db.ensure_default_wallet(user.id)

    text = (
        f"Xin chào **{user.first_name}**! 👋\n\n"
        "Tôi là **Bot Quản Lý Thu Chi AI** 💰\n\n"
        "**Nói chuyện tự nhiên (text / thoại / ảnh):**\n"
        "• `chi 45k cafe bằng MoMo`\n"
        "• `thu 8tr lương`\n"
        "• `tạo ví Vietcombank`\n"
        "• `chuyển 500k từ tiền mặt sang MoMo`\n"
        "• `số dư ví MoMo` / `danh sách ví`\n"
        "• Gửi **ảnh hóa đơn** → bot tự đọc & ghi nhận\n"
        "• Gửi **tin nhắn thoại** → bot tự nghe\n\n"
        "**Lệnh nhanh:** /balance /wallets /list /report /predict /chart /help\n\n"
        "Bot nhắc bạn cuối ngày (21:00) 🌙"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **HƯỚNG DẪN ĐẦY ĐỦ**\n\n"
        "**1. Thêm giao dịch**\n"
        "`chi 50k ăn trưa` · `chi 200k xăng bằng MoMo`\n"
        "`thu 12tr lương vào Vietcombank`\n\n"
        "**2. Ví / Tài khoản**\n"
        "`tạo ví MoMo` · `tạo ví Techcombank`\n"
        "`danh sách ví` · `số dư ví MoMo`\n"
        "`chuyển 500k từ tiền mặt sang MoMo`\n\n"
        "**3. Sửa / Xóa**\n"
        "`sửa #12 thành 60k` · `xóa #5`\n\n"
        "**4. Báo cáo & Biểu đồ**\n"
        "`số dư` · `báo cáo` · `dự đoán` · `biểu đồ danh mục`\n\n"
        "**5. Ảnh hóa đơn**\n"
        "Chỉ cần gửi ảnh hóa đơn / biên lai → Bot OCR tự động\n\n"
        "**6. Tin nhắn thoại**\n"
        "Nhấn mic và nói bình thường\n\n"
        "**7. Nhắc nhở**\n"
        "`bật nhắc nhở` · `tắt nhắc nhở` · `nhắc lúc 20h`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await db.get_balance(update.effective_user.id)
    await update.message.reply_text(format_balance(data), parse_mode="Markdown")


async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallets = await db.get_wallets(update.effective_user.id)
    await update.message.reply_text(format_wallets(wallets), parse_mode="Markdown")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txs = await db.get_transactions(update.effective_user.id, limit=10)
    await update.message.reply_text(format_list(txs), parse_mode="Markdown")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await db.get_report(update.effective_user.id, days=30)
    await update.message.reply_text(format_report(data), parse_mode="Markdown")


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await db.get_month_prediction_data(update.effective_user.id)
    await update.message.reply_text(format_prediction(data), parse_mode="Markdown")


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_chart(update, "category")


async def send_chart(update: Update, chart_type: str = "category"):
    user_id = update.effective_user.id
    thinking = await update.message.reply_text("📊 Đang vẽ biểu đồ...")

    try:
        if chart_type == "category":
            report = await db.get_report(user_id, days=30)
            img_bytes = create_category_chart(report["by_category"], "Chi tiêu 30 ngày theo danh mục")
            caption = "📊 Biểu đồ chi tiêu theo danh mục (30 ngày)"
        elif chart_type == "income_expense":
            report = await db.get_report(user_id, days=30)
            img_bytes = create_income_expense_chart(
                report["income"], report["expense"], "Thu vs Chi (30 ngày)"
            )
            caption = "📊 So sánh Thu nhập & Chi tiêu (30 ngày)"
        else:
            stats = await db.get_daily_stats(user_id, days=30)
            img_bytes = create_daily_chart(stats, days=30)
            caption = "📈 Xu hướng thu chi theo ngày (30 ngày)"

        await thinking.delete()
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(img_bytes), filename="chart.png"),
            caption=caption
        )
    except Exception as e:
        logger.exception("Chart error")
        await thinking.edit_text(f"⚠️ Không vẽ được biểu đồ: {str(e)[:100]}")


async def execute_action(update: Update, context: ContextTypes.DEFAULT_TYPE, thinking, result: dict, user_id: int):
    """Xử lý chung kết quả từ AI (text / voice / image)"""
    action = result.get("action", "chat")
    params = result.get("params", {})
    reply = result.get("reply", "")

    # ----- ADD TRANSACTION -----
    if action == "add_transaction":
        type_ = params.get("type", "expense")
        amount = float(params.get("amount", 0))
        category = params.get("category", "Khác")
        description = params.get("description", "")
        wallet_name = params.get("wallet_name")

        if amount <= 0:
            await thinking.edit_text("❌ Số tiền không hợp lệ.")
            return

        wallet_id = None
        if wallet_name:
            wallet = await db.get_wallet_by_name(user_id, wallet_name)
            if not wallet:
                # Tự tạo ví nếu chưa có
                wtype = "momo" if "momo" in wallet_name.lower() else \
                        "zalopay" if "zalo" in wallet_name.lower() else \
                        "bank" if any(x in wallet_name.lower() for x in ["bank", "vietcom", "techcom", "tpbank", "mb", "acb", "bidv"]) else "other"
                wallet_id = await db.create_wallet(user_id, wallet_name, wtype)
            else:
                wallet_id = wallet["id"]
        else:
            wallet_id = await db.ensure_default_wallet(user_id)

        tx_id = await db.add_transaction(user_id, type_, amount, category, description, wallet_id)

        if not reply:
            icon = "📥" if type_ == "income" else "📤"
            wname = wallet_name or "Tiền mặt"
            reply = f"{icon} Đã thêm `#{tx_id}` — {format_money(amount)} ({wname})"
        await thinking.edit_text(reply, parse_mode="Markdown")

    # ----- UPDATE -----
    elif action == "update_transaction":
        tx_id = int(params.get("tx_id", 0))
        wallet_id = None
        if "wallet_name" in params:
            w = await db.get_wallet_by_name(user_id, params["wallet_name"])
            if w:
                wallet_id = w["id"]

        success = await db.update_transaction(
            user_id=user_id,
            tx_id=tx_id,
            type_=params.get("type"),
            amount=float(params["amount"]) if "amount" in params else None,
            category=params.get("category"),
            description=params.get("description"),
            wallet_id=wallet_id,
        )
        if success:
            tx = await db.get_transaction(user_id, tx_id)
            await thinking.edit_text(
                f"✅ Đã cập nhật `#{tx_id}`\n"
                f"{'📥' if tx['type']=='income' else '📤'} {format_money(tx['amount'])} — {tx['description'] or tx['category']}",
                parse_mode="Markdown"
            )
        else:
            await thinking.edit_text(f"❌ Không tìm thấy giao dịch #{tx_id}")

    # ----- DELETE -----
    elif action == "delete_transaction":
        tx_id = int(params.get("tx_id", 0))
        success = await db.delete_transaction(user_id, tx_id)
        if success:
            await thinking.edit_text(f"🗑️ Đã xóa giao dịch `#{tx_id}`", parse_mode="Markdown")
        else:
            await thinking.edit_text(f"❌ Không tìm thấy giao dịch #{tx_id}")

    # ----- BALANCE -----
    elif action == "get_balance":
        wallet_name = params.get("wallet_name")
        if wallet_name:
            wallet = await db.get_wallet_by_name(user_id, wallet_name)
            if not wallet:
                await thinking.edit_text(f"❌ Không tìm thấy ví **{wallet_name}**", parse_mode="Markdown")
                return
            data = await db.get_balance(user_id, wallet_id=wallet["id"])
            await thinking.edit_text(format_balance(data, wallet_name), parse_mode="Markdown")
        else:
            data = await db.get_balance(user_id)
            await thinking.edit_text(format_balance(data), parse_mode="Markdown")

    # ----- LIST -----
    elif action == "get_list":
        limit = int(params.get("limit", 10))
        txs = await db.get_transactions(user_id, limit=limit)
        await thinking.edit_text(format_list(txs), parse_mode="Markdown")

    # ----- REPORT -----
    elif action == "get_report":
        days = int(params.get("days", 30))
        data = await db.get_report(user_id, days=days)
        await thinking.edit_text(format_report(data), parse_mode="Markdown")

    # ----- PREDICTION -----
    elif action == "get_prediction":
        data = await db.get_month_prediction_data(user_id)
        await thinking.edit_text(format_prediction(data), parse_mode="Markdown")

    # ----- CHART -----
    elif action == "get_chart":
        chart_type = params.get("chart_type", "category")
        await thinking.delete()
        await send_chart(update, chart_type)

    # ----- CREATE WALLET -----
    elif action == "create_wallet":
        name = params.get("name", "").strip()
        wtype = params.get("type", "other")
        if not name:
            await thinking.edit_text("❌ Tên ví không được để trống.")
            return
        wallet_id = await db.create_wallet(user_id, name, wtype)
        if reply:
            await thinking.edit_text(reply, parse_mode="Markdown")
        else:
            await thinking.edit_text(f"🆕 Đã tạo ví **{name}** thành công!", parse_mode="Markdown")

    # ----- LIST WALLETS -----
    elif action == "list_wallets":
        wallets = await db.get_wallets(user_id)
        await thinking.edit_text(format_wallets(wallets), parse_mode="Markdown")

    # ----- TRANSFER -----
    elif action == "transfer":
        from_name = params.get("from_wallet", "Tiền mặt")
        to_name = params.get("to_wallet")
        amount = float(params.get("amount", 0))
        desc = params.get("description", "")

        if not to_name or amount <= 0:
            await thinking.edit_text("❌ Thiếu thông tin ví đích hoặc số tiền không hợp lệ.")
            return

        from_w = await db.get_wallet_by_name(user_id, from_name)
        to_w = await db.get_wallet_by_name(user_id, to_name)

        if not from_w:
            await thinking.edit_text(f"❌ Không tìm thấy ví nguồn **{from_name}**", parse_mode="Markdown")
            return
        if not to_w:
            # Tự tạo ví đích nếu chưa có
            wtype = "momo" if "momo" in to_name.lower() else "other"
            to_id = await db.create_wallet(user_id, to_name, wtype)
            to_w = {"id": to_id, "name": to_name}

        try:
            tx_out, tx_in = await db.transfer(user_id, from_w["id"], to_w["id"], amount, desc)
            await thinking.edit_text(
                f"🔄 Đã chuyển **{format_money(amount)}**\n"
                f"Từ **{from_w['name']}** → **{to_w['name']}**\n"
                f"`#{tx_out}` → `#{tx_in}`",
                parse_mode="Markdown"
            )
        except Exception as e:
            await thinking.edit_text(f"❌ Lỗi chuyển tiền: {str(e)[:100]}")

    # ----- REMIND -----
    elif action == "set_remind":
        enabled = params.get("enabled", True)
        hour = int(params.get("hour", REMIND_HOUR))
        await db.set_remind_setting(user_id, enabled=enabled, hour=hour)
        if reply:
            await thinking.edit_text(reply, parse_mode="Markdown")
        else:
            status = "bật" if enabled else "tắt"
            await thinking.edit_text(f"🔔 Đã {status} nhắc nhở (lúc {hour}:00)")

    elif action == "help":
        await thinking.delete()
        await help_command(update, context)

    else:
        await thinking.edit_text(reply or "Mình chưa hiểu rõ 😅", parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    thinking = await update.message.reply_text("⏳ Đang xử lý...")

    try:
        result = await process_message(text, user_id)
        await execute_action(update, context, thinking, result, user_id)
    except Exception as e:
        logger.exception("Error handling message")
        await thinking.edit_text(f"⚠️ Có lỗi: {str(e)[:150]}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.voice:
        return

    user_id = update.effective_user.id
    voice = update.message.voice
    thinking = await update.message.reply_text("🎧 Đang nghe và nhận diện...")

    try:
        tg_file = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        result = await process_voice(audio_bytes, user_id, mime_type="audio/ogg")
        await execute_action(update, context, thinking, result, user_id)
    except Exception as e:
        logger.exception("Error handling voice")
        await thinking.edit_text(f"⚠️ Không xử lý được tin nhắn thoại: {str(e)[:120]}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý ảnh hóa đơn → OCR bằng Gemini"""
    if not update.message or not update.message.photo:
        return

    user_id = update.effective_user.id
    # Lấy ảnh độ phân giải cao nhất
    photo = update.message.photo[-1]
    thinking = await update.message.reply_text("🧾 Đang đọc hóa đơn...")

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())

        # Gemini hỗ trợ image/jpeg tốt
        result = await process_image(image_bytes, user_id, mime_type="image/jpeg")
        await execute_action(update, context, thinking, result, user_id)
    except Exception as e:
        logger.exception("Error handling photo")
        await thinking.edit_text(f"⚠️ Không đọc được ảnh: {str(e)[:120]}")


# Đăng ký handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("balance", balance_command))
application.add_handler(CommandHandler("wallets", wallets_command))
application.add_handler(CommandHandler("list", list_command))
application.add_handler(CommandHandler("report", report_command))
application.add_handler(CommandHandler("predict", predict_command))
application.add_handler(CommandHandler("chart", chart_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.AUDIO, handle_voice))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))


# ========== NHẮC NHỞ ==========
async def send_daily_reminders():
    logger.info("Running daily reminder job...")
    try:
        user_ids = await db.get_users_to_remind(hour=REMIND_HOUR)
        for uid in user_ids:
            try:
                data = await db.get_month_prediction_data(uid)
                text = format_daily_reminder(data)
                await application.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to remind user {uid}: {e}")
    except Exception as e:
        logger.exception("Daily reminder job failed")


# ========== FASTAPI ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database (Neon Postgres)...")
    await db.init_db()

    await application.initialize()

    render_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if render_url:
        if not render_url.startswith("http"):
            render_url = f"https://{render_url}"
        webhook_url = f"{render_url}/webhook/{WEBHOOK_SECRET}"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        logger.info(f"Webhook set: {webhook_url}")
    else:
        logger.warning("No RENDER_EXTERNAL_URL → polling mode")
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

    scheduler.add_job(
        send_daily_reminders,
        CronTrigger(hour=REMIND_HOUR, minute=0, timezone="Asia/Ho_Chi_Minh"),
        id="daily_reminder",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started – reminder at {REMIND_HOUR}:00 VN")

    yield

    scheduler.shutdown(wait=False)
    if not (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")):
        await application.updater.stop()
        await application.stop()
    else:
        await application.bot.delete_webhook()
    await application.shutdown()
    await db.close_db()
    logger.info("Bot stopped.")


app = FastAPI(title="Telegram Thu Chi Bot AI", lifespan=lifespan)


@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "service": "Telegram Thu Chi Bot – Gemini + Neon + Wallets + OCR",
        "time": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        return Response(status_code=403)
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)


@app.post("/cron/daily-reminder")
async def cron_daily_reminder(request: Request):
    await send_daily_reminders()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
