# SuperAssets Telegram Bot

This version is intentionally restricted to checking the Telegram user's own
phone number: the user must share their Telegram contact and the contact must
belong to the same Telegram account.

## Files
- bot.py
- requirements.txt
- .env.example

## Run
1. Install Python 3.10+.
2. `pip install -r requirements.txt`
3. Set environment variables from `.env.example`.
4. Run: `python bot.py`

The API call is:
POST https://superassets.in/api/v1/check

Headers:
- X-API-Key
- Content-Type: application/json

JSON body:
{"service": "<service id>", "number": "<user's shared phone number>"}

The service IDs were taken from the `/api/v1/services` response shown in the
screenshots supplied in this conversation.
