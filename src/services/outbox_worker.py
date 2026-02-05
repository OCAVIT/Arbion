"""
Outbox worker for sending queued Telegram messages.

Runs as a background task, checking the outbox table for
pending messages and sending them via Telegram.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db_context
from src.models import OutboxMessage, OutboxStatus
from src.services.telegram_client import get_telegram_service

logger = logging.getLogger(__name__)


def calculate_typing_delay(text: str) -> float:
    """
    Calculate realistic typing delay based on message length.
    Simulates human typing speed (about 40-60 chars per second with pauses).
    """
    char_count = len(text)
    # Base delay: 1-2 seconds for short messages
    # Plus ~0.05-0.1 seconds per character (simulating ~10-20 chars/sec typing)
    base_delay = random.uniform(1.0, 2.5)
    char_delay = char_count * random.uniform(0.03, 0.07)
    total = base_delay + char_delay
    # Cap at 8 seconds max
    return min(total, 8.0)


async def process_outbox_message(
    message: OutboxMessage,
    db: AsyncSession,
) -> bool:
    """
    Process a single outbox message.

    Returns:
        True if message was sent successfully
    """
    telegram = get_telegram_service()
    if not telegram:
        logger.warning("Telegram service not available")
        return False

    try:
        # Calculate realistic typing delay for human-like behavior
        typing_delay = calculate_typing_delay(message.message_text)

        success = await telegram.send_message(
            message.recipient_id,
            message.message_text,
            typing_delay=typing_delay,
        )

        if success:
            message.status = OutboxStatus.SENT
            message.sent_at = datetime.now(timezone.utc)
            logger.info(f"Outbox message {message.id} sent successfully")
        else:
            message.status = OutboxStatus.FAILED
            message.error_message = "Failed to send via Telegram"
            logger.error(f"Outbox message {message.id} failed to send")

        return success

    except Exception as e:
        message.status = OutboxStatus.FAILED
        message.error_message = str(e)
        logger.error(f"Outbox message {message.id} error: {e}")
        return False


async def outbox_worker_iteration(db: AsyncSession) -> int:
    """
    Process one batch of pending outbox messages.

    Returns:
        Number of messages processed
    """
    # Get pending messages
    result = await db.execute(
        select(OutboxMessage)
        .where(OutboxMessage.status == OutboxStatus.PENDING)
        .order_by(OutboxMessage.created_at)
        .limit(10)
    )
    messages = result.scalars().all()

    if not messages:
        return 0

    processed = 0
    for message in messages:
        await process_outbox_message(message, db)
        processed += 1
        # Small delay between messages to avoid rate limits
        await asyncio.sleep(1)

    await db.commit()
    return processed


async def run_outbox_worker(interval_seconds: int = 10):
    """
    Run the outbox worker continuously.

    Args:
        interval_seconds: Time between checks for new messages
    """
    logger.info(f"Starting outbox worker (interval: {interval_seconds}s)")

    while True:
        try:
            async with get_db_context() as db:
                processed = await outbox_worker_iteration(db)
                if processed > 0:
                    logger.debug(f"Outbox worker processed {processed} messages")
        except Exception as e:
            logger.error(f"Outbox worker error: {e}")

        await asyncio.sleep(interval_seconds)
