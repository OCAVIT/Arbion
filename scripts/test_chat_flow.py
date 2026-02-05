"""
Test the AI chatting flow manually.

This script simulates the AI negotiator sending a message to a seller
and receiving a response. Use this to test the chat flow between
your main account and bot account.

Usage:
    python scripts/test_chat_flow.py --seller-id YOUR_MAIN_ACCOUNT_ID

The bot will send a test message to your main account,
then you can reply and verify the system receives it.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.config import settings


async def test_chat_flow(seller_id: int):
    """Test sending message from bot to seller."""

    if not settings.tg_session_string:
        print("ERROR: TG_SESSION_STRING not configured in .env")
        return

    print("\nInitializing Telegram client (bot account)...")

    client = TelegramClient(
        StringSession(settings.tg_session_string),
        settings.tg_api_id,
        settings.tg_api_hash,
    )

    await client.start()
    me = await client.get_me()

    print(f"Logged in as: {me.first_name} (ID: {me.id})")
    print(f"Target seller ID: {seller_id}")

    # Send test message
    test_message = """Здравствуйте!

Заинтересовал ваш товар из объявления.
Ещё актуально? Готов обсудить условия.

[Это тестовое сообщение от AI-бота]"""

    print(f"\nSending test message to {seller_id}...")

    try:
        entity = await client.get_entity(seller_id)
        await client.send_message(entity, test_message)
        print("Message sent successfully!")
        print("\n" + "="*50)
        print("Now reply from your main account.")
        print("The bot will show received messages below.")
        print("Press Ctrl+C to stop.")
        print("="*50 + "\n")

        # Listen for replies
        @client.on(events.NewMessage(from_users=seller_id))
        async def handler(event):
            print(f"\n[RECEIVED] From {seller_id}:")
            print(f"  {event.message.text}")
            print(f"  (message_id: {event.message.id})")

            # Auto-reply to test full flow
            await asyncio.sleep(2)
            await event.reply("Спасибо за ответ! Какая цена с торгом? [AI auto-reply]")
            print("[SENT] AI auto-reply")

        await client.run_until_disconnected()

    except ValueError:
        print(f"ERROR: User {seller_id} not found")
        print("Make sure:")
        print("  1. The user ID is correct")
        print("  2. The bot account has interacted with this user before")
        print("  3. Or try using username instead: @username")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test AI chat flow")
    parser.add_argument("--seller-id", type=int, required=True, help="Seller's Telegram user ID")

    args = parser.parse_args()

    asyncio.run(test_chat_flow(args.seller_id))
