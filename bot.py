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
    """Start command - welcome message and service selection"""
    context.user_data.clear()
    await update.message.reply_text(
        "👋 <b>Welcome!</b>\n\n"
        "This bot checks account status across multiple services.\n\n"
        "<b>📋 Step 1: Choose a Service</b>",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    context.user_data.clear()
    await update.message.reply_text(
        "✅ Cancelled.\n\nSend /start to begin again.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True),
    )


async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input and check for action buttons"""
    text = (update.message.text or "").strip()
    
    # Handle action buttons
    if text == "🔄 Check Again":
        service = context.user_data.get("service")
        if service:
            emoji = SERVICE_EMOJIS.get(service, "✓")
            await update.message.reply_text(
                f"{emoji} <b>Service: {service.upper()}</b>\n\n"
                "<b>📱 Enter Phone Number:</b>\n"
                "<i>Example: 9876543210</i>",
                parse_mode="HTML",
                reply_markup=contact_keyboard(),
            )
        return
    
    if text == "🔀 Change Service":
        context.user_data.clear()
        await update.message.reply_text(
            "👋 <b>Welcome!</b>\n\n"
            "This bot checks account status across multiple services.\n\n"
            "<b>📋 Step 1: Choose a Service</b>",
            parse_mode="HTML",
            reply_markup=service_keyboard(),
        )
        return
    
    if text.lower() == "cancel" or text == "❌ Cancel":
        await cancel(update, context)
        return

    # Otherwise, process as phone number
    await check_number_and_call_api(update, context)


async def number_or_service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route incoming message to service or number handler"""
    if not context.user_data.get("service"):
        await service_received(update, context)
    else:
        await number_received(update, context)


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle service selection and ask for phone number"""
    text = update.message.text.strip()
    
    if text.lower() == "cancel" or text == "❌ Cancel":
        await cancel(update, context)
        return

    # Extract service name from emoji + text format
    service = text.replace("❌ Cancel", "").strip()
    selected_service = None
    
    for s in SERVICES:
        if s.lower() in service.lower():
            selected_service = s.lower()
            break
    
    if not selected_service:
        await update.message.reply_text(
            "❌ <b>Invalid Service</b>\n\n"
            "Please select from the buttons below.",
            parse_mode="HTML",
            reply_markup=service_keyboard(),
        )
        return

    # Save selected service and ask for number
    context.user_data["service"] = selected_service
    emoji = SERVICE_EMOJIS.get(selected_service, "✓")
    
    await update.message.reply_text(
        f"{emoji} <b>Service Selected: {selected_service.upper()}</b>\n\n"
        "<b>📱 Step 2: Enter Your Phone Number</b>\n"
        "Please enter your mobile number (with country code +91):\n"
        "<i>Example: 9876543210</i>",
        parse_mode="HTML",
        reply_markup=contact_keyboard(),
    )


async def check_number_and_call_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validate number and call API"""
    text = (update.message.text or "").strip()
    
    if text.lower() == "cancel" or text == "❌ Cancel":
        await cancel(update, context)
        return

    # Get or normalize phone number - handle with or without +91
    number = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # If starts with just digits (common Indian format), add +91
    if not number.startswith("+") and not number.startswith("0"):
        number = "+91" + number
    elif number.startswith("0"):
        number = "+91" + number[1:]
    elif not number.startswith("+"):
        # If it's just digits or has country code without +, normalize
        if number.isdigit():
            number = "+91" + number
    
    digits = number[1:] if number.startswith("+") else number
    
    # Validation checks
    if not digits.isdigit():
        await update.message.reply_text(
            "❌ <b>Invalid Format</b>\n\n"
            "Please enter only numbers (no letters or special characters).\n"
            "<i>Example: 9876543210</i>",
            parse_mode="HTML",
            reply_markup=contact_keyboard(),
        )
        return
    
    if len(digits) != 10:
        await update.message.reply_text(
            "❌ <b>Invalid Number</b>\n\n"
            "Please enter a 10-digit mobile number.\n"
            "<i>Example: 9876543210</i>",
            parse_mode="HTML",
            reply_markup=contact_keyboard(),
        )
        return

    service = context.user_data.get("service")
    if not service:
        await update.message.reply_text(
            "⚠️ <b>Session Expired</b>\n\n"
            "Please send /start and select a service again.",
            parse_mode="HTML",
        )
        return

    if not API_KEY:
        await update.message.reply_text("❌ API key is not configured on the bot.")
        return

    # Save the number and show loading state
    context.user_data["number"] = number
    emoji = SERVICE_EMOJIS.get(service, "✓")
    
    await update.message.reply_text(
        f"⏳ <b>Checking {service.upper()}...</b>\n"
        f"{emoji} Service: <b>{service.upper()}</b>\n"
        f"📱 Number: <b>+91{digits}</b>",
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
            header = f"<b>✅ {emoji} {service.upper()} - Result</b>\n\n"
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

    # Show action buttons - Check Again or Change Service
    action_keyboard = ReplyKeyboardMarkup(
        [
            ["🔄 Check Again", "🔀 Change Service"],
            ["❌ Cancel"]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    
    await update.message.reply_text(
        "What would you like to do?",
        reply_markup=action_keyboard,
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
