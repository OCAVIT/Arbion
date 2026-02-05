"""
Telegram client service using Telethon.

Handles:
- Receiving messages from monitored chats
- Sending messages to sellers
- Outbox worker for queued messages
"""

import asyncio
import logging
from typing import Callable, Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramService:
    """
    Telegram client wrapper using Telethon.

    Usage:
        telegram = TelegramService()
        await telegram.start()
        telegram.on_new_message(handler)
        await telegram.run()
    """

    def __init__(self):
        """Initialize the Telegram client."""
        if not settings.tg_session_string:
            logger.warning("TG_SESSION_STRING not configured, Telegram will be disabled")
            self.client = None
            return

        self.client = TelegramClient(
            StringSession(settings.tg_session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
        )
        self.me = None
        self._message_handlers = []

    async def start(self):
        """Start the Telegram client and authenticate."""
        if not self.client:
            logger.warning("Telegram client not initialized")
            return

        await self.client.start()
        self.me = await self.client.get_me()
        logger.info(f"Telegram logged in as: {self.me.first_name} (ID: {self.me.id})")

    async def stop(self):
        """Disconnect the Telegram client."""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client disconnected")

    def on_new_message(self, handler: Callable):
        """
        Register a handler for new messages.

        Args:
            handler: Async function that receives (event, telegram_service)
        """
        if not self.client:
            return

        @self.client.on(events.NewMessage)
        async def wrapper(event):
            try:
                await handler(event, self)
            except Exception as e:
                logger.error(f"Message handler error: {e}")

        self._message_handlers.append(wrapper)

    async def send_message(self, recipient_id: int, text: str) -> bool:
        """
        Send a message to a user or chat.

        Args:
            recipient_id: Telegram user/chat ID
            text: Message text to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.client:
            logger.warning("Cannot send message: Telegram client not initialized")
            return False

        try:
            entity = await self.client.get_entity(recipient_id)
            await self.client.send_message(entity, text)
            logger.info(f"Message sent to {recipient_id}")
            return True
        except ValueError:
            logger.error(f"User {recipient_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def get_entity(self, entity_id: int):
        """Get a Telegram entity by ID."""
        if not self.client:
            return None
        try:
            return await self.client.get_entity(entity_id)
        except Exception as e:
            logger.error(f"Failed to get entity {entity_id}: {e}")
            return None

    def is_own_message(self, sender_id: int) -> bool:
        """Check if a message is from our own account."""
        return self.me is not None and sender_id == self.me.id

    async def run_until_disconnected(self):
        """Run the client until disconnected."""
        if self.client:
            await self.client.run_until_disconnected()


# Global instance
telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> Optional[TelegramService]:
    """Get the global Telegram service instance."""
    global telegram_service
    return telegram_service


async def init_telegram_service() -> TelegramService:
    """Initialize and start the global Telegram service."""
    global telegram_service
    telegram_service = TelegramService()
    await telegram_service.start()
    return telegram_service
