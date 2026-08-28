import os
import json
import logging
import re
from typing import Any

import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

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
    "gosats": "💰", "bigbasket": "🛒", "meesho": "🛍️", "plutos": "🪙",
    "starexch": "⭐", "swiggy": "🍔", "flipkart": "🛒", "shein": "👗",
    "myntra": "👚", "oyo": "🏨", "mantrimall": "🏪", "blinkit": "⚡",
    "brevistay": "🛏️", "ajio": "👟", "amazon": "📦", "jio": "📱",
    "crownit": "👑", "telegram": "✈️", "whatsapp": "💬",
    "habuildyoga": "🧘", "lenskart": "👓"
}


def service_label(service: str) -> str:
    return f"{SERVICE_EMOJIS.get(service, '🔹')} {service.title()}"


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 2):
        row = [service_label(SERVICES[i])]
        if i + 1 < len(SERVICES):
            row.append(service_label(SERVICES[i + 1]))
        rows.append(row)
    rows.append(["↩️ Change / Cancel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, input_field_placeholder="Choose a service…")


def number_keyboard():
    return ReplyKeyboardMarkup([["↩️ Change / Cancel"]], resize_keyboard=True, input_field_placeholder="Enter mobile number…")


def escape_html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_result(data: Any) -> str:
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = str(data)
    if len(text) > 3900:
        text = text[:3890] + "\n... (response truncated)"
    return f"<b>📊 API response</b>\n<pre>{escape_html(text)}</pre>"


def normalize_service(text: str):
    value = text.strip().casefold()
    for service in SERVICES:
        if value == service.casefold() or value == service_label(service).casefold():
            return service
    # Also tolerate emoji/punctuation around a valid service name.
    words = re.sub(r"[^a-z0-9]+", " ", value).strip().split()
    compact = "".join(words)
    for service in SERVICES:
        if compact == service.casefold():
            return service
    return None


def normalize_number(text: str):
    """Return a clean phone number. Indian 10-digit numbers get +91."""
    value = text.strip()
    # Remove common separators while preserving a leading +.
    value = re.sub(r"[\s().-]", "", value)

    if value.startswith("+"):
        digits = "+" + re.sub(r"\D", "", value[1:])
        if re.fullmatch(r"\+[1-9]\d{7,14}", digits):
            return digits
        return None

    digits = re.sub(r"\D", "", value)
    if re.fullmatch(r"[6-9]\d{9}", digits):
        return "+91" + digits
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "✨ <b>Service Checker</b>\n\n"
        "Select a service below to continue.\n"
        "<i>You’ll enter the mobile number after selecting a service.</i>",
        reply_markup=service_keyboard(),
        parse_mode="HTML",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "↩️ Cancelled.\n\nChoose a service to start again:",
        reply_markup=service_keyboard(),
    )


async def service_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.strip().lower() in {"cancel", "❌ cancel", "↩️ change / cancel"}:
        await cancel(update, context)
        return

    service = normalize_service(text)
    if not service:
        await update.message.reply_text(
            "⚠️ Please choose a service using the buttons below.",
            reply_markup=service_keyboard(),
        )
        return

    context.user_data["service"] = service
    await update.message.reply_text(
        f"{SERVICE_EMOJIS.get(service, '🔹')} <b>{service.title()}</b> selected.\n\n"
        "📱 <b>Enter mobile number</b>\n"
        "Example: <code>9876543210</code> or <code>+919876543210</code>",
        reply_markup=number_keyboard(),
        parse_mode="HTML",
    )


async def number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.strip().lower() in {"cancel", "❌ cancel", "↩️ change / cancel"}:
        await cancel(update, context)
        return

    service = context.user_data.get("service")
    if not service:
        await update.message.reply_text(
            "⚠️ Please select a service first:",
            reply_markup=service_keyboard(),
        )
        return

    number = normalize_number(text)
    if not number:
        await update.message.reply_text(
            "❌ Invalid mobile number.\n\n"
            "For India, send a 10-digit number such as <code>9876543210</code>, "
            "or use international format such as <code>+919876543210</code>.",
            reply_markup=number_keyboard(),
            parse_mode="HTML",
        )
        return

    if not API_KEY:
        await update.message.reply_text("❌ API key is not configured on the bot.")
        return

    await update.message.reply_text(
        f"⏳ Checking <b>{service.title()}</b> for <code>{escape_html(number)}</code>...",
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
            await update.message.reply_text(format_result(data), parse_mode="HTML")
        elif response.status_code == 401:
            await update.message.reply_text("❌ API authorization failed (401). Check SUPERASSETS_API_KEY.")
        elif response.status_code == 422:
            await update.message.reply_text("❌ Invalid request (422). The API rejected the service/number format.")
        else:
            await update.message.reply_text(
                f"❌ API returned HTTP {response.status_code}.\n\n{format_result(data)}",
                parse_mode="HTML",
            )

    except requests.RequestException as e:
        log.exception("API request failed")
        await update.message.reply_text(
            f"❌ Could not reach the API.\n<code>{escape_html(e)}</code>",
            parse_mode="HTML",
        )

    # Let the user choose another service without needing /start.
    await update.message.reply_text(
        "\n✨ <b>What would you like to check next?</b>",
        reply_markup=service_keyboard(),
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

    # Service-first flow: a text message is routed according to whether
    # a service has already been selected.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            route_text,
        )
    )

    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("service"):
        # A service button should switch services even when a previous
        # service is already stored.
        selected = normalize_service(update.message.text or "")
        if selected:
            await service_received(update, context)
        else:
            await number_received(update, context)
    else:
        await service_received(update, context)


if __name__ == "__main__":
    main()
