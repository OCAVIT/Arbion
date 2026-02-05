"""
Message handler for incoming Telegram messages.

Handles:
- Saving raw messages to database
- Parsing buy/sell patterns
- Creating orders from detected patterns
"""

import logging
import re
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.db import get_db_context
from src.models import Order, OrderType, RawMessage

logger = logging.getLogger(__name__)

# Patterns for detecting buy/sell intent
BUY_PATTERNS = [
    r'\b(куплю|покупаю|ищу|нужен|нужна|нужно|приму|возьму)\b',
]
SELL_PATTERNS = [
    r'\b(продам|продаю|отдам|есть в наличии|в наличии|готов продать)\b',
]

# Price pattern: matches numbers with optional currency
PRICE_PATTERN = r'(\d[\d\s]*(?:[.,]\d+)?)\s*(?:руб|р|₽|\$|usd|грн|€|euro)?'


def detect_order_type(text: str) -> Optional[OrderType]:
    """
    Detect if message is a buy or sell order.

    Args:
        text: Message text to analyze

    Returns:
        OrderType.BUY, OrderType.SELL, or None if not detected
    """
    text_lower = text.lower()

    for pattern in BUY_PATTERNS:
        if re.search(pattern, text_lower):
            return OrderType.BUY

    for pattern in SELL_PATTERNS:
        if re.search(pattern, text_lower):
            return OrderType.SELL

    return None


def extract_price(text: str) -> Optional[Decimal]:
    """
    Extract price from message text.

    Args:
        text: Message text

    Returns:
        Decimal price or None if not found
    """
    match = re.search(PRICE_PATTERN, text.lower())
    if match:
        try:
            price_str = match.group(1).replace(' ', '').replace(',', '.')
            return Decimal(price_str)
        except Exception:
            pass
    return None


def extract_product(text: str, order_type: OrderType) -> str:
    """
    Extract product name from message.

    Simple heuristic: take the text after the buy/sell keyword.

    Args:
        text: Message text
        order_type: Detected order type

    Returns:
        Product name or cleaned text
    """
    text_lower = text.lower()

    # Patterns to remove
    patterns = BUY_PATTERNS if order_type == OrderType.BUY else SELL_PATTERNS

    result = text
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # Clean up
    result = re.sub(r'\s+', ' ', result).strip()

    # Limit length
    if len(result) > 200:
        result = result[:200]

    return result if result else text[:200]


async def handle_new_message(event, telegram_service) -> None:
    """
    Handle incoming Telegram message.

    Args:
        event: Telethon NewMessage event
        telegram_service: TelegramService instance
    """
    try:
        # Skip own messages
        if telegram_service.is_own_message(event.sender_id):
            return

        # Skip empty messages
        if not event.text:
            return

        message = event.message
        chat = await event.get_chat()

        chat_id = event.chat_id
        message_id = message.id
        sender_id = event.sender_id
        chat_title = getattr(chat, 'title', None) or getattr(chat, 'first_name', '') or str(chat_id)
        raw_text = event.text

        logger.info(f"New message from {chat_title} ({chat_id}): {raw_text[:50]}...")

        async with get_db_context() as db:
            # Save raw message (upsert to handle duplicates)
            stmt = insert(RawMessage).values(
                chat_id=chat_id,
                message_id=message_id,
                sender_id=sender_id,
                chat_title=chat_title,
                raw_text=raw_text,
                processed=False,
            ).on_conflict_do_nothing(
                index_elements=['chat_id', 'message_id']
            )
            await db.execute(stmt)

            # Detect order type
            order_type = detect_order_type(raw_text)

            if order_type:
                # Extract product and price
                product = extract_product(raw_text, order_type)
                price = extract_price(raw_text)

                # Check if order already exists
                existing = await db.execute(
                    select(Order).where(
                        Order.chat_id == chat_id,
                        Order.message_id == message_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    # Create order
                    order = Order(
                        order_type=order_type,
                        chat_id=chat_id,
                        sender_id=sender_id,
                        message_id=message_id,
                        product=product,
                        price=price,
                        raw_text=raw_text,
                        is_active=True,
                    )
                    db.add(order)

                    logger.info(
                        f"Created {order_type.value} order: {product[:50]} "
                        f"(price: {price}, chat: {chat_id})"
                    )

            # Mark raw message as processed
            result = await db.execute(
                select(RawMessage).where(
                    RawMessage.chat_id == chat_id,
                    RawMessage.message_id == message_id,
                )
            )
            raw_msg = result.scalar_one_or_none()
            if raw_msg:
                raw_msg.processed = True

            await db.commit()

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
