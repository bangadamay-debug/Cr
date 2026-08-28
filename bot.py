import os
import json
import logging
from typing import Any

import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_KEY = os.getenv("SUPERASSETS_API_KEY", "").strip()
API_BASE = os.getenv("SUPERASSETS_API_BASE", "https://superassets.in/api/v1").rstrip("/")

SERVICES = [
    "gosats", "bigbasket", "meesho", "plutos", "starexch", "swiggy",
    "flipkart", "shein", "myntra", "oyo", "mantrimall", "blinkit",
    "brevistay", "ajio", "amazon", "jio", "crownit", "telegram",
    "whatsapp", "habuildyoga", "lenskart"
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


SERVICE_LABELS = {
    "gosats": "🪙 GoSats", "bigbasket": "🛒 BigBasket", "meesho": "🛍️ Meesho",
    "plutos": "💳 Plutos", "starexch": "⭐ StarExch", "swiggy": "🍔 Swiggy",
    "flipkart": "🛒 Flipkart", "shein": "👗 SHEIN", "myntra": "👕 Myntra",
    "oyo": "🏨 OYO", "mantrimall": "🛍️ MantriMall", "blinkit": "⚡ Blinkit",
    "brevistay": "🏨 Brevistay", "ajio": "👟 AJIO", "amazon": "📦 Amazon",
    "jio": "📱 Jio", "crownit": "👑 Crownit", "telegram": "✈️ Telegram",
    "whatsapp": "💬 WhatsApp", "habuildyoga": "🧘 HaBuildYoga", "lenskart": "👓 Lenskart",
}


def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 2):
        rows.append([SERVICE_LABELS.get(x, x.title()) for x in SERVICES[i:i+2]])
    rows.append(["❌ Cancel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def number_keyboard():
    return ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True)


def service_from_text(text: str):
    cleaned = text.strip().lower()
    if cleaned in ("cancel", "❌ cancel"):
        return "cancel"
    for key, label in SERVICE_LABELS.items():
        if cleaned == label.lower() or cleaned == key:
            return key
    return None

def normalize_number(value: str):
    value = value.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+") and value[1:].isdigit():
        digits = value[1:]
        if 8 <= len(digits) <= 15:
            return "+" + digits
    if value.isdigit() and len(value) == 10:
        return "+91" + value
    return None


def format_result(data: Any) -> str:
    # The API response schema was not shown in the supplied screenshots,
    # so display the returned JSON without inventing field names.
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = str(data)
    if len(text) > 3900:
        text = text[:3890] + "\n... (response truncated)"
    return f"API response:\n<pre>{escape_html(text)}</pre>"


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["waiting_for_service"] = True
    await update.message.reply_text(
        "✨ <b>Welcome to the Checker</b>\n\n"
        "1️⃣ Select a service below.\n"
        "2️⃣ Then enter the mobile number to check.\n\n"
        "Choose a service to continue:",
        reply_markup=service_keyboard(),
        parse_mode="HTML",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🛑 <b>Cancelled.</b>\n\nSend /start whenever you want to begin again.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
        parse_mode="HTML",
    )


async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_number"):
        return await service_received(update, context)

    text = update.message.text.strip()
    if text.lower() in ("cancel", "❌ cancel"):
        await cancel(update, context)
        return

    number = normalize_number(text)
    if not number:
        await update.message.reply_text(
            "❌ <b>Invalid number</b>\n\n"
            "Please enter a valid 10-digit Indian number, such as <code>9876543210</code>, "
            "or include the country code, such as <code>+919876543210</code>.",
            reply_markup=number_keyboard(),
            parse_mode="HTML",
        )
        return

    context.user_data["number"] = number
    context.user_data["waiting_for_number"] = False

    await check_selected_service(update, context)


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_service"):
        await update.message.reply_text(
            "ℹ️ Send /start to begin a new check.",
            reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
        )
        return

    service = service_from_text(update.message.text)
    if service == "cancel":
        await cancel(update, context)
        return
    if service is None:
        await update.message.reply_text(
            "⚠️ Please tap one of the service buttons below.",
            reply_markup=service_keyboard(),
        )
        return

    context.user_data["service"] = service
    context.user_data["waiting_for_service"] = False
    context.user_data["waiting_for_number"] = True

    await update.message.reply_text(
        f"✅ <b>{SERVICE_LABELS.get(service, service.title())}</b> selected.\n\n"
        "📱 Now enter the mobile number you want to check.\n"
        "Example: <code>9876543210</code> or <code>+919876543210</code>",
        reply_markup=number_keyboard(),
        parse_mode="HTML",
    )


async def check_selected_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service = context.user_data.get("service")
    number = context.user_data.get("number")

    if not service or not number:
        await update.message.reply_text("⚠️ Session expired. Send /start again.")
        return

    if not API_KEY:
        await update.message.reply_text("❌ API key is not configured on the bot.")
        return

    await update.message.reply_text(
        f"🔎 Checking <b>{SERVICE_LABELS.get(service, service.title())}</b>...\n"
        f"📱 Number: <code>{escape_html(number)}</code>",
        parse_mode="HTML",
    )

    try:
        response = requests.post(
            f"{API_BASE}/check",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
            },
            json={"service": service, "number": number},
            timeout=30,
        )

        try:
            data = response.json()
        except ValueError:
            data = response.text

        if response.status_code == 200:
            await update.message.reply_text(
                "✅ <b>Check complete</b>\n\n" + format_result(data),
                parse_mode="HTML",
                reply_markup=service_keyboard(),
            )
        elif response.status_code == 401:
            await update.message.reply_text("❌ API authorization failed (401). Check SUPERASSETS_API_KEY.")
        elif response.status_code == 422:
            await update.message.reply_text("❌ Invalid request (422). The API rejected the service/number format.")
        else:
            await update.message.reply_text(
                f"❌ API returned HTTP {response.status_code}.\n" + format_result(data),
                parse_mode="HTML",
            )
    except requests.RequestException as e:
        log.exception("API request failed")
        await update.message.reply_text(
            f"❌ Could not reach the API.\n{escape_html(str(e))}",
            parse_mode="HTML",
        )


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_service"):
        await service_received(update, context)
    elif context.user_data.get("waiting_for_number"):
        await number_received(update, context)
    else:
        await update.message.reply_text("ℹ️ Send /start to begin a new check.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not API_KEY:
        raise RuntimeError("SUPERASSETS_API_KEY is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))

    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
