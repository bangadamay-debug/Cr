import os
import json
import logging
from typing import Any

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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


def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 2):
        rows.append(SERVICES[i:i+2])
    rows.append(["Cancel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def contact_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share my phone number", request_contact=True)],
         ["Cancel"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


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
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "This bot checks only the phone number belonging to the Telegram "
        "account using the contact you share.\n\n"
        "First, share your own phone number:",
        reply_markup=contact_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Cancelled. Send /start to begin again.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
    )


async def contact_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact

    if contact.user_id != update.effective_user.id:
        await update.message.reply_text(
            "❌ Please use the Telegram contact button to share your own number. "
            "Another person's contact cannot be checked."
        )
        return

    number = contact.phone_number.replace(" ", "").replace("-", "")
    context.user_data["number"] = number

    await update.message.reply_text(
        "✅ Number received.\n\nChoose a service:",
        reply_markup=service_keyboard(),
    )


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service = update.message.text.strip().lower()

    if service == "cancel":
        await cancel(update, context)
        return

    if service not in SERVICES:
        await update.message.reply_text("Please select a service from the buttons.")
        return

    number = context.user_data.get("number")
    if not number:
        await update.message.reply_text(
            "Session expired. Send /start and share your number again."
        )
        return

    if not API_KEY:
        await update.message.reply_text("❌ API key is not configured on the bot.")
        return

    await update.message.reply_text("⏳ Checking...")

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
                format_result(data), parse_mode="HTML"
            )
        elif response.status_code == 401:
            await update.message.reply_text(
                "❌ API authorization failed (401). Check SUPERASSETS_API_KEY."
            )
        elif response.status_code == 422:
            await update.message.reply_text(
                "❌ Invalid request (422). The API rejected the service/number format."
            )
        else:
            await update.message.reply_text(
                f"❌ API returned HTTP {response.status_code}.\n"
                f"{format_result(data)}",
                parse_mode="HTML",
            )

    except requests.RequestException as e:
        log.exception("API request failed")
        await update.message.reply_text(
            f"❌ Could not reach the API.\n{escape_html(str(e))}",
            parse_mode="HTML",
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not API_KEY:
        raise RuntimeError("SUPERASSETS_API_KEY is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.CONTACT, contact_received))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, service_received))

    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
