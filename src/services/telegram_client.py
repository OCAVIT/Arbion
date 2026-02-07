"""
Telegram client service using Telethon.

Handles:
- Receiving messages from monitored chats
- Sending messages to sellers
- Outbox worker for queued messages
"""

import asyncio
import logging
import random
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
        logger.info(f"Initializing Telegram client...")
        logger.info(f"TG_API_ID configured: {bool(settings.tg_api_id)}")
        logger.info(f"TG_API_HASH configured: {bool(settings.tg_api_hash)}")
        logger.info(f"TG_SESSION_STRING configured: {bool(settings.tg_session_string)}")

        if not settings.tg_session_string:
            logger.warning("TG_SESSION_STRING not configured, Telegram will be disabled")
            self.client = None
            return

        if not settings.tg_api_id or not settings.tg_api_hash:
            logger.warning("TG_API_ID or TG_API_HASH not configured, Telegram will be disabled")
            self.client = None
            return

        self.client = TelegramClient(
            StringSession(settings.tg_session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
        )
        self.me = None
        self._message_handlers = []
        logger.info("Telegram client initialized successfully")

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
                # Mark incoming message as read
                try:
                    await event.message.mark_read()
                except Exception:
                    pass
                await handler(event, self)
            except Exception as e:
                logger.error(f"Message handler error: {e}")

        self._message_handlers.append(wrapper)

    async def send_message(self, recipient_id: int, text: str, typing_delay: float = 0) -> int | None:
        """
        Send a message to a user or chat.

        Args:
            recipient_id: Telegram user/chat ID
            text: Message text to send
            typing_delay: Seconds to show "typing" before sending (0 = no typing)

        Returns:
            Telegram message ID if sent successfully, None otherwise.
            For backwards compatibility, truthy (int) means success, falsy (None) means failure.
        """
        if not self.client:
            logger.warning("Cannot send message: Telegram client not initialized")
            return None

        try:
            entity = await self.client.get_entity(recipient_id)

            # Show typing indicator if delay is set
            if typing_delay > 0:
                async with self.client.action(entity, 'typing'):
                    await asyncio.sleep(typing_delay)

            sent_msg = await self.client.send_message(entity, text)
            # Mark their messages as read so it shows "read" in Telegram
            try:
                await self.client.send_read_acknowledge(entity)
            except Exception:
                pass  # Non-critical, don't fail the send
            logger.info(f"Message sent to {recipient_id} (msg_id={sent_msg.id})")
            return sent_msg.id
        except ValueError:
            logger.error(f"User {recipient_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None

    async def send_file(
        self,
        recipient_id: int,
        file_path: str,
        caption: str = None,
        force_document: bool = False,
    ) -> int | None:
        """
        Send a file (photo/document) to a user or chat.

        Args:
            recipient_id: Telegram user/chat ID
            file_path: Path to the file on disk
            caption: Optional text caption
            force_document: If True, send as document even for images

        Returns:
            Telegram message ID if sent successfully, None otherwise.
        """
        if not self.client:
            logger.warning("Cannot send file: Telegram client not initialized")
            return None

        try:
            entity = await self.client.get_entity(recipient_id)
            sent_msg = await self.client.send_file(
                entity,
                file_path,
                caption=caption,
                force_document=force_document,
            )
            try:
                await self.client.send_read_acknowledge(entity)
            except Exception:
                pass
            logger.info(f"File sent to {recipient_id} (msg_id={sent_msg.id})")
            return sent_msg.id
        except ValueError:
            logger.error(f"User {recipient_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to send file: {e}")
            return None

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
