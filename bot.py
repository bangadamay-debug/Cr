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


def confirm_keyboard():
    return ReplyKeyboardMarkup(
        [["✅ Confirm", "❌ Cancel"]],
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
        "Type the mobile number you want to check (10-digit Indian number).\n"
        "For privacy, do not send OTPs, passwords, or account numbers.\n\n"
        "Example: 9876543210",
        reply_markup=number_keyboard(),
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

    if value.lower() == "cancel":
        await cancel(update, context)
        return

    # Step 1: accept a typed mobile number.
    if "number" not in context.user_data:
        digits = re.sub(r"\D", "", value)
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]

        if len(digits) != 10 or not digits.isdigit() or digits[0] not in "6789":
            await message.reply_text(
                "❌ Please enter a valid 10-digit Indian mobile number.\n"
                "Example: 9876543210"
            )
            return

        context.user_data["pending_number"] = digits
        await message.reply_text(
            f"You entered: {digits}\n\n"
            "Please confirm that you own this number or have permission to check it.",
            reply_markup=confirm_keyboard(),
        )
        return

    # Step 2: service selection.
    service = value.lower()
    if service not in SERVICES:
        await message.reply_text("Please select a service from the buttons.")
        return

    number = context.user_data["number"]

    if not API_KEY:
        await message.reply_text("❌ API key is not configured on the bot.")
        return

    await message.reply_text("⏳ Checking...")

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
            await message.reply_text(format_result(data), parse_mode="HTML")
        elif response.status_code == 401:
            await message.reply_text(
                "❌ API authorization failed (401). Check SUPERASSETS_API_KEY."
            )
        elif response.status_code == 422:
            await message.reply_text(
                "❌ Invalid request (422). The API rejected the service/number format."
            )
        else:
            await message.reply_text(
                f"❌ API returned HTTP {response.status_code}.\n"
                f"{format_result(data)}",
                parse_mode="HTML",
            )

    except requests.RequestException as e:
        log.exception("API request failed")
        await message.reply_text(
            f"❌ Could not reach the API.\n{escape_html(str(e))}",
            parse_mode="HTML",
        )


async def confirmation_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()

    if value == "❌ Cancel":
        await cancel(update, context)
        return

    if value != "✅ Confirm":
        await update.message.reply_text(
            "Please tap ✅ Confirm or ❌ Cancel.",
            reply_markup=confirm_keyboard(),
        )
        return

    number = context.user_data.pop("pending_number", None)
    if not number:
        await update.message.reply_text("Session expired. Send /start again.")
        return

    context.user_data["number"] = number
    await update.message.reply_text(
        "✅ Confirmed.\n\nChoose a service:",
        reply_markup=service_keyboard(),
    )

async def number_or_service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("number"):
        await service_received(update, context)
    else:
        await number_received(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not API_KEY:
        raise RuntimeError("SUPERASSETS_API_KEY is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^(✅ Confirm|❌ Cancel)$"),
            confirmation_received,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, service_received))

    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()

    if raw.lower() in ("cancel", "❌ cancel"):
        await cancel(update, context)
        return

    number = re.sub(r"[^0-9]", "", raw)
    if len(number) != 10 or number[0] not in "6789":
        await update.message.reply_text(
            "❌ <b>Invalid Number</b>\n\n"
            "Please enter a valid 10-digit Indian mobile number.\n"
            "Example: <code>9876543210</code>",
            parse_mode="HTML",
        )
        return

    context.user_data["number"] = number

    await update.message.reply_text(
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "      🛍 <b>SELECT CHECKER</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Choose the service you want to check:",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )

