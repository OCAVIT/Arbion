"""
Message handler for incoming Telegram messages.

Handles:
- Saving raw messages to database
- Parsing buy/sell patterns with product, price, region extraction
- Creating orders from detected patterns
- Matching buy/sell orders to create deals
"""

import logging
import re
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.db import get_db_context
from src.models import (
    DetectedDeal, DealStatus, Negotiation, NegotiationStage,
    Order, OrderType, RawMessage
)
from src.services.ai_negotiator import initiate_negotiation, process_seller_response, process_buyer_response

logger = logging.getLogger(__name__)

# Patterns for detecting buy/sell intent
BUY_KEYWORDS = [
    'куплю', 'покупаю', 'ищу', 'нужен', 'нужна', 'нужно',
    'приму', 'возьму', 'куплю срочно', 'ищу срочно'
]
SELL_KEYWORDS = [
    'продам', 'продаю', 'отдам', 'есть в наличии', 'в наличии',
    'готов продать', 'продам срочно', 'срочно продам'
]

# Known product patterns (common electronics, etc.)
PRODUCT_PATTERNS = [
    r'(iphone\s*\d+\s*(?:pro\s*)?(?:max)?)',
    r'(айфон\s*\d+\s*(?:про\s*)?(?:макс)?)',
    r'(samsung\s*(?:galaxy\s*)?[sa]\d+\s*(?:ultra)?)',
    r'(самсунг\s*(?:галакси\s*)?[sa]\d+\s*(?:ультра)?)',
    r'(macbook\s*(?:air|pro)?\s*(?:m\d)?)',
    r'(макбук\s*(?:эйр|про)?\s*(?:м\d)?)',
    r'(ipad\s*(?:air|pro|mini)?)',
    r'(airpods\s*(?:pro|max)?)',
    r'(playstation\s*\d+|ps\s*\d+)',
    r'(xbox\s*(?:series\s*)?[xs]?)',
    r'(nintendo\s*switch)',
]

# Price patterns - more specific to avoid matching model numbers
PRICE_PATTERNS = [
    r'(?:цена|за|стоит|стоимость|прошу|отдам за|продам за)[:\s]*(\d[\d\s]*(?:[.,]\d+)?)\s*(?:т\.?р\.?|тыс\.?|к|руб|р|₽|\$)?',
    r'(\d[\d\s]*(?:[.,]\d+)?)\s*(?:т\.?р\.?|тыс\.?|тысяч|к)\b',
    r'(\d{2,}[\d\s]*(?:[.,]\d+)?)\s*(?:руб|р|₽)\b',
]

# Region patterns
REGIONS = [
    'москва', 'мск', 'питер', 'спб', 'санкт-петербург', 'петербург',
    'новосибирск', 'екатеринбург', 'казань', 'нижний новгород',
    'челябинск', 'самара', 'омск', 'ростов', 'уфа', 'красноярск',
    'пермь', 'воронеж', 'волгоград', 'краснодар', 'саратов',
    'тюмень', 'тольятти', 'ижевск', 'барнаул', 'ульяновск',
    'иркутск', 'хабаровск', 'ярославль', 'владивосток', 'махачкала',
    'томск', 'оренбург', 'кемерово', 'новокузнецк', 'рязань',
]

# Normalize region names
REGION_NORMALIZE = {
    'мск': 'Москва',
    'москва': 'Москва',
    'спб': 'Санкт-Петербург',
    'питер': 'Санкт-Петербург',
    'санкт-петербург': 'Санкт-Петербург',
    'петербург': 'Санкт-Петербург',
}


def detect_order_type(text: str) -> Optional[OrderType]:
    """Detect if message is a buy or sell order."""
    text_lower = text.lower()

    for keyword in BUY_KEYWORDS:
        if keyword in text_lower:
            return OrderType.BUY

    for keyword in SELL_KEYWORDS:
        if keyword in text_lower:
            return OrderType.SELL

    return None


def extract_product(text: str) -> str:
    """
    Extract product name using known patterns.
    Falls back to extracting text near buy/sell keyword.
    """
    text_lower = text.lower()

    # Try known product patterns first
    for pattern in PRODUCT_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            product = match.group(1).strip()
            # Capitalize properly
            return product.title().replace('Iphone', 'iPhone').replace('Macbook', 'MacBook').replace('Ipad', 'iPad').replace('Airpods', 'AirPods')

    # Fallback: extract text after buy/sell keyword
    all_keywords = BUY_KEYWORDS + SELL_KEYWORDS
    for keyword in all_keywords:
        if keyword in text_lower:
            idx = text_lower.find(keyword)
            after_keyword = text[idx + len(keyword):].strip()
            # Take first meaningful chunk (up to comma, newline, or price mention)
            chunk = re.split(r'[,\n]|(?:\d+\s*(?:т\.?р|тыс|к|руб|р|₽))', after_keyword)[0].strip()
            if chunk and len(chunk) > 3:
                # Clean up
                chunk = re.sub(r'^[!.\s]+', '', chunk)
                chunk = chunk[:100]  # Limit length
                return chunk if chunk else "Товар"

    return "Товар"


def extract_price(text: str) -> Optional[Decimal]:
    """
    Extract price from message text.
    Handles formats like: 100к, 100 тыс, 100000 руб, цена 100к
    """
    text_lower = text.lower()

    for pattern in PRICE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            try:
                price_str = match.group(1).replace(' ', '').replace(',', '.')
                price = Decimal(price_str)

                # Check if followed by 'к' or 'тыс' multiplier
                full_match = match.group(0).lower()
                if any(m in full_match for m in ['к', 'тыс', 'т.р', 'тр']):
                    price *= 1000

                # Sanity check - prices usually between 1000 and 10000000
                if 1000 <= price <= 10000000:
                    return price
            except Exception:
                pass

    return None


def extract_region(text: str) -> Optional[str]:
    """Extract region/city from message text."""
    text_lower = text.lower()

    for region in REGIONS:
        if region in text_lower:
            # Return normalized name if available
            return REGION_NORMALIZE.get(region, region.title())

    return None


async def try_match_orders(db, new_order: Order) -> Optional[DetectedDeal]:
    """
    Try to match a new order with existing opposite orders.
    Buy order matches with Sell orders and vice versa.
    """
    opposite_type = OrderType.SELL if new_order.order_type == OrderType.BUY else OrderType.BUY

    # Find matching orders by product similarity
    # Simple approach: exact product match or similar
    product_lower = new_order.product.lower() if new_order.product else ""

    # Get active opposite orders
    result = await db.execute(
        select(Order).where(
            and_(
                Order.order_type == opposite_type,
                Order.is_active == True,
                Order.id != new_order.id,
            )
        ).order_by(Order.created_at.desc()).limit(50)
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        candidate_product = (candidate.product or "").lower()

        # Check if products match (simple substring match for now)
        # In production, use embeddings/vector similarity
        if product_lower and candidate_product:
            # Check for common product keywords
            keywords = ['iphone', 'samsung', 'macbook', 'ipad', 'airpods', 'playstation', 'xbox']
            for kw in keywords:
                if kw in product_lower and kw in candidate_product:
                    # Found a match!
                    buy_order = new_order if new_order.order_type == OrderType.BUY else candidate
                    sell_order = candidate if new_order.order_type == OrderType.BUY else new_order

                    # Calculate prices and margin
                    buy_price = buy_order.price or Decimal('0')
                    sell_price = sell_order.price or Decimal('0')
                    margin = buy_price - sell_price if buy_price and sell_price else Decimal('0')

                    # Create deal
                    deal = DetectedDeal(
                        buy_order_id=buy_order.id,
                        sell_order_id=sell_order.id,
                        product=buy_order.product or sell_order.product or "Товар",
                        region=buy_order.region or sell_order.region,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        margin=margin,
                        status=DealStatus.COLD,
                        buyer_chat_id=buy_order.chat_id,
                        buyer_sender_id=buy_order.sender_id,
                    )
                    db.add(deal)
                    await db.flush()  # Get deal ID and ensure it's persisted

                    # Explicitly set relationships so they're available without refresh
                    deal.sell_order = sell_order
                    deal.buy_order = buy_order

                    # Mark orders as matched (deactivate)
                    buy_order.is_active = False
                    sell_order.is_active = False

                    logger.info(f"Created deal #{deal.id}: {deal.product} (margin: {margin})")
                    return deal

    return None


async def check_negotiation_response(db, sender_id: int, message_text: str) -> bool:
    """
    Check if incoming message is a response to an active negotiation.
    If so, process it with AI negotiator.

    Args:
        db: Database session
        sender_id: Telegram sender ID
        message_text: Message text

    Returns:
        True if message was a negotiation response
    """
    if not sender_id:
        return False

    # First, check if this is a SELLER response
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(
            and_(
                or_(
                    Negotiation.seller_sender_id == sender_id,
                    Negotiation.seller_chat_id == sender_id,
                ),
                Negotiation.stage.in_([
                    NegotiationStage.INITIAL,
                    NegotiationStage.CONTACTED,
                    NegotiationStage.NEGOTIATING,
                    NegotiationStage.WARM,
                    NegotiationStage.HANDED_TO_MANAGER,
                ]),
            )
        )
    )
    negotiation = result.scalar_one_or_none()

    if negotiation:
        logger.info(f"Found active negotiation {negotiation.id} for seller {sender_id}")
        await process_seller_response(negotiation, message_text, db)
        return True

    # Then, check if this is a BUYER response
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .join(DetectedDeal, Negotiation.deal_id == DetectedDeal.id)
        .where(
            and_(
                or_(
                    DetectedDeal.buyer_sender_id == sender_id,
                    DetectedDeal.buyer_chat_id == sender_id,
                ),
                Negotiation.stage.in_([
                    NegotiationStage.INITIAL,
                    NegotiationStage.CONTACTED,
                    NegotiationStage.NEGOTIATING,
                    NegotiationStage.WARM,
                    NegotiationStage.HANDED_TO_MANAGER,
                ]),
            )
        )
    )
    negotiation = result.scalar_one_or_none()

    if negotiation:
        logger.info(f"Found active negotiation {negotiation.id} for buyer {sender_id}")
        await process_buyer_response(negotiation, message_text, db)
        return True

    return False


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
        sender = await event.get_sender()

        chat_id = event.chat_id
        message_id = message.id
        # In channels, sender_id can be None - use chat_id as fallback
        sender_id = event.sender_id or chat_id
        chat_title = getattr(chat, 'title', None) or getattr(chat, 'first_name', '') or str(chat_id)
        raw_text = event.text

        # Extract contact info (username or chat info)
        sender_username = getattr(sender, 'username', None) if sender else None
        chat_username = getattr(chat, 'username', None)
        contact_info = f"@{sender_username}" if sender_username else (f"@{chat_username}" if chat_username else f"chat:{chat_id}")

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
                # Extract product, price, and region
                product = extract_product(raw_text)
                price = extract_price(raw_text)
                region = extract_region(raw_text)

                logger.info(f"Parsed: type={order_type.value}, product={product}, price={price}, region={region}")

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
                        region=region,
                        raw_text=raw_text,
                        contact_info=contact_info,
                        is_active=True,
                    )
                    db.add(order)
                    await db.flush()  # Get order ID

                    logger.info(
                        f"Created {order_type.value} order #{order.id}: {product} "
                        f"(price: {price}, region: {region})"
                    )

                    # Try to match with opposite orders
                    deal = await try_match_orders(db, order)
                    if deal:
                        logger.info(f"Auto-matched into deal #{deal.id}")
                        # Start AI negotiation for new deal
                        await initiate_negotiation(deal, db)
            else:
                # Only check for negotiation response if this wasn't a new order
                # (to avoid treating the order message as a response)
                await check_negotiation_response(db, sender_id, raw_text)

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
