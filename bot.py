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

SERVICE_EMOJIS = {
    "gosats": "🎮", "bigbasket": "🛒", "meesho": "📦", "plutos": "🎯",
    "starexch": "⭐", "swiggy": "🍔", "flipkart": "🛍️", "shein": "👗",
    "myntra": "👔", "oyo": "🏨", "mantrimall": "🏬", "blinkit": "⚡",
    "brevistay": "🏩", "ajio": "🎁", "amazon": "📦", "jio": "📱",
    "crownit": "👑", "telegram": "✈️", "whatsapp": "💬", "habuildyoga": "🧘",
    "lenskart": "👓"
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def service_keyboard():
    """Create a 2-column keyboard with service options"""
    rows = []
    service_labels = [
        f"{SERVICE_EMOJIS.get(s, '•')} {s.capitalize()}" 
        for s in SERVICES
    ]
    for i in range(0, len(service_labels), 2):
        rows.append(service_labels[i:i+2])
    rows.append(["❌ Cancel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def contact_keyboard():
    """Create contact input keyboard"""
    return ReplyKeyboardMarkup(
        [["❌ Cancel"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def format_result(data: Any) -> str:
    """Format API response with better styling"""
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = str(data)
    
    if len(text) > 3900:
        text = text[:3890] + "\n... (response truncated)"
    
    return f"<b>📊 Result:</b>\n<pre>{escape_html(text)}</pre>"


def escape_html(s: str) -> str:
    """Escape HTML special characters"""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - welcome message and number entry"""
    context.user_data.clear()
    await update.message.reply_text(
        "👋 <b>Welcome!</b>\n\n"
        "This bot checks account status across multiple services.\n\n"
        "<b>📱 Step 1: Enter Your Phone Number</b>\n"
        "Please share your mobile number with the country code:\n"
        "<i>Example: +919876543210</i>",
        parse_mode="HTML",
        reply_markup=contact_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    context.user_data.clear()
    await update.message.reply_text(
        "✅ Cancelled.\n\nSend /start to begin again.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
    )


async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input"""
    text = (update.message.text or "").strip()
    if text.lower() == "cancel" or text == "❌ Cancel":
        await cancel(update, context)
        return

    # Normalize phone number
    number = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if number.startswith("00"):
        number = "+" + number[2:]

    digits = number[1:] if number.startswith("+") else number
    
    # Validation checks
    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        await update.message.reply_text(
            "❌ <b>Invalid Number Format</b>\n\n"
            "Please enter a valid phone number (8-15 digits).\n"
            "<i>Example: +919876543210</i>",
            parse_mode="HTML",
            reply_markup=contact_keyboard(),
        )
        return

    if not number.startswith("+"):
        await update.message.reply_text(
            "❌ <b>Country Code Required</b>\n\n"
            "Your number needs the country code prefix.\n"
            "<i>Example: +919876543210 (for India)</i>",
            parse_mode="HTML",
            reply_markup=contact_keyboard(),
        )
        return

    context.user_data["number"] = number
    await update.message.reply_text(
        f"✅ <b>Number Saved:</b> {escape_html(number)}\n\n"
        "<b>📋 Step 2: Choose a Service</b>",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )


async def number_or_service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route incoming message to number or service handler"""
    if not context.user_data.get("number"):
        await number_received(update, context)
    else:
        await service_received(update, context)


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle service selection"""
    text = update.message.text.strip()
    
    if text.lower() == "cancel" or text == "❌ Cancel":
        await cancel(update, context)
        return

    # Extract service name from emoji + text format
    service = text.replace("❌ Cancel", "").strip()
    for s in SERVICES:
        if s.lower() in service.lower():
            service = s.lower()
            break
    else:
        await update.message.reply_text(
            "❌ <b>Invalid Service</b>\n\n"
            "Please select from the buttons below.",
            parse_mode="HTML",
            reply_markup=service_keyboard(),
        )
        return

    number = context.user_data.get("number")
    if not number:
        await update.message.reply_text(
            "⚠️ <b>Session Expired</b>\n\n"
            "Please send /start and share your number again.",
            parse_mode="HTML",
        )
        return

    if not API_KEY:
        await update.message.reply_text("❌ API key is not configured on the bot.")
        return

    # Show loading state
    await update.message.reply_text(
        f"⏳ Checking <b>{service.upper()}</b>...\n"
        f"<i>Number: {escape_html(number)}</i>",
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
            emoji = SERVICE_EMOJIS.get(service, "✓")
            header = f"<b>{emoji} {service.upper()} - Check Complete</b>\n\n"
            await update.message.reply_text(
                header + format_result(data),
                parse_mode="HTML",
            )
        elif response.status_code == 401:
            await update.message.reply_text(
                "❌ <b>Authorization Failed (401)</b>\n\n"
                "API key configuration error. Please contact the admin.",
                parse_mode="HTML",
            )
        elif response.status_code == 422:
            await update.message.reply_text(
                "❌ <b>Invalid Request (422)</b>\n\n"
                "The service or number format was not accepted by the API.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"❌ <b>API Error (HTTP {response.status_code})</b>\n\n"
                f"{format_result(data)}",
                parse_mode="HTML",
            )

    except requests.RequestException as e:
        log.exception("API request failed")
        await update.message.reply_text(
            f"❌ <b>Connection Error</b>\n\n"
            f"Could not reach the API:\n"
            f"<i>{escape_html(str(e))}</i>",
            parse_mode="HTML",
        )

    # Offer to check another service
    await update.message.reply_text(
        "🔄 Check another service?",
        reply_markup=service_keyboard(),
    )


def main():
    """Start the bot"""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not API_KEY:
        raise RuntimeError("SUPERASSETS_API_KEY is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, number_or_service_received))

    log.info("Bot started successfully")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
