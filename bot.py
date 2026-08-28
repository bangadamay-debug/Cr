import os
import json
import logging
import re
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


def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 3):
        rows.append([f"🔎 {s.title()}" for s in SERVICES[i:i+3]])
    rows.append(["🔄 New Number", "❌ Cancel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def number_keyboard():
    return ReplyKeyboardMarkup(
        [["Cancel"]],
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
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "      🛍 <b>SELECT CHECKER</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Choose the service you want to check:",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       ❌ <b>CANCELLED</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Send /start whenever you're ready.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
    )


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    value = message.text.strip()

    if value.lower() in ("cancel", "❌ cancel"):
        await cancel(update, context)
        return

    # Accept the service buttons while preserving their displayed UI.
    service = re.sub(r"^[^A-Za-z0-9]*", "", value).strip().lower()
    if service not in SERVICES:
        await message.reply_text(
            "⚠️ Please select a service using the buttons below.",
            reply_markup=service_keyboard(),
        )
        return

    context.user_data["service"] = service
    await message.reply_text(
        f"📱 <b>{service.title()}</b> selected.\n\n"
        "Enter the 10-digit mobile number to check:",
        parse_mode="HTML",
        reply_markup=number_keyboard(),
    )


async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()

    if raw.lower() in ("cancel", "❌ cancel"):
        await cancel(update, context)
        return

    service = context.user_data.get("service")
    if not service:
        await update.message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━━━╮\n"
            "      🛍 <b>SELECT CHECKER</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Please select a service first.",
            parse_mode="HTML",
            reply_markup=service_keyboard(),
        )
        return

    number = re.sub(r"\D", "", raw)
    if number.startswith("91") and len(number) == 12:
        number = number[2:]

    if len(number) != 10 or number[0] not in "6789":
        await update.message.reply_text(
            "❌ <b>Invalid Number</b>\n\n"
            "Please enter a valid 10-digit Indian mobile number.\n"
            "Example: <code>9876543210</code>",
            parse_mode="HTML",
            reply_markup=number_keyboard(),
        )
        return

    context.user_data["number"] = number

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
            await update.message.reply_text(format_result(data), parse_mode="HTML")
            await update.message.reply_text(
                "🔄 Want to check another service?",
                reply_markup=service_keyboard(),
            )
            context.user_data.pop("number", None)
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


async def text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Once a service is selected, the next text is treated as the number.
    if context.user_data.get("service"):
        await number_received(update, context)
    else:
        await service_received(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not API_KEY:
        raise RuntimeError("SUPERASSETS_API_KEY is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_received))

    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)




if __name__ == "__main__":
    main()
