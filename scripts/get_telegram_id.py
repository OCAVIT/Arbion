"""
Get Telegram user ID and chat ID using Telethon.

Usage:
    python scripts/get_telegram_id.py

Required environment variables:
    TG_API_ID - Your Telegram API ID (from my.telegram.org)
    TG_API_HASH - Your Telegram API Hash
    TG_PHONE - Your phone number (for first login)

Or provide session string:
    TG_SESSION_STRING - Existing session string (skip phone auth)
"""

import asyncio
import os

from telethon import TelegramClient
from telethon.sessions import StringSession


async def get_ids():
    """Get your Telegram user ID and list recent chats."""
    api_id = int(os.environ.get("TG_API_ID", 0))
    api_hash = os.environ.get("TG_API_HASH", "")
    session_string = os.environ.get("TG_SESSION_STRING", "")
    phone = os.environ.get("TG_PHONE", "")

    if not api_id or not api_hash:
        print("ERROR: TG_API_ID and TG_API_HASH required")
        print("Get them from https://my.telegram.org/apps")
        return

    if session_string:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        client = TelegramClient("temp_session", api_id, api_hash)

    await client.start(phone=phone if phone else None)

    # Get own info
    me = await client.get_me()
    print("\n" + "="*50)
    print("YOUR TELEGRAM INFO")
    print("="*50)
    print(f"User ID: {me.id}")
    print(f"Username: @{me.username}" if me.username else "Username: (not set)")
    print(f"Name: {me.first_name} {me.last_name or ''}")
    print(f"Phone: {me.phone}")

    # Generate session string if not provided
    if not session_string:
        new_session = client.session.save()
        print(f"\nSession String (save this!):\n{new_session}")

    # List recent dialogs
    print("\n" + "="*50)
    print("RECENT CHATS (for finding chat IDs)")
    print("="*50)

    dialogs = await client.get_dialogs(limit=20)
    for d in dialogs:
        chat_type = "User" if d.is_user else ("Group" if d.is_group else "Channel")
        print(f"[{chat_type}] {d.name}: {d.id}")

    await client.disconnect()

    print("\n" + "="*50)
    print("""
To use these IDs for testing:

1. Set your bot account's TG_SESSION_STRING in .env
2. Run seed script with your IDs:

   python scripts/seed_test_data.py \\
       --main-id YOUR_USER_ID \\
       --bot-id BOT_USER_ID \\
       --chat-id -100CHAT_ID

Note: Group/channel IDs are negative (e.g., -1001234567890)
""")


if __name__ == "__main__":
    asyncio.run(get_ids())
