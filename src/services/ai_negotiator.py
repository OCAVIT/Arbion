"""
AI Negotiator service for warming up cold leads.

Handles:
- Sending initial contact messages to sellers
- Processing seller responses
- Progressing deals from COLD -> IN_PROGRESS -> WARM
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import (
    DealStatus,
    DetectedDeal,
    MessageRole,
    Negotiation,
    NegotiationMessage,
    NegotiationStage,
    OutboxMessage,
    OutboxStatus,
)

logger = logging.getLogger(__name__)

# Initial contact templates
INITIAL_TEMPLATES = [
    "Здравствуйте! Увидел ваше объявление о {product}. Ещё актуально? Интересует покупка.",
    "Добрый день! {product} ещё продаёте? Готов рассмотреть.",
    "Привет! По поводу {product} - актуально? Интересует.",
]

# Follow-up templates based on seller response
FOLLOWUP_INTERESTED = [
    "Отлично! Подскажите, какое состояние? И возможен ли торг?",
    "Хорошо! А что по состоянию? Комплект полный?",
]

FOLLOWUP_PRICE_CHECK = [
    "Понял. А по цене можно подвинуться? Готов забрать сегодня.",
    "Ясно. Если немного уступите - заберу сразу.",
]

# Keywords that indicate seller interest
POSITIVE_KEYWORDS = [
    'да', 'актуально', 'есть', 'продаю', 'готов', 'можно',
    'конечно', 'пишите', 'звоните', 'в наличии', 'ок', 'ok',
]

NEGATIVE_KEYWORDS = [
    'нет', 'продано', 'неактуально', 'не продаю', 'забронировано',
    'уже нет', 'sold', 'занято',
]

PRICE_KEYWORDS = [
    'цена', 'стоит', 'рублей', 'тысяч', 'руб', '₽', 'торг',
]


def analyze_response(text: str) -> str:
    """
    Analyze seller's response to determine next action.

    Returns:
        'positive' - seller interested, continue negotiation
        'negative' - seller not interested, close deal
        'price' - seller mentioned price, discuss further
        'unclear' - need clarification
    """
    text_lower = text.lower()

    # Check for negative signals first
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in text_lower:
            return 'negative'

    # Check for price discussion
    for keyword in PRICE_KEYWORDS:
        if keyword in text_lower:
            return 'price'

    # Check for positive signals
    for keyword in POSITIVE_KEYWORDS:
        if keyword in text_lower:
            return 'positive'

    return 'unclear'


def generate_response(stage: str, product: str, context: str = "") -> str:
    """
    Generate AI response based on negotiation stage.

    Args:
        stage: Current stage ('initial', 'positive', 'price', 'unclear')
        product: Product name
        context: Previous conversation context

    Returns:
        Generated response message
    """
    import random

    if stage == 'initial':
        template = random.choice(INITIAL_TEMPLATES)
        return template.format(product=product)

    elif stage == 'positive':
        return random.choice(FOLLOWUP_INTERESTED)

    elif stage == 'price':
        return random.choice(FOLLOWUP_PRICE_CHECK)

    else:
        # Default follow-up
        return "Подскажите подробнее, пожалуйста."


async def initiate_negotiation(deal: DetectedDeal, db: AsyncSession) -> Optional[Negotiation]:
    """
    Start negotiation for a cold deal.
    Creates Negotiation record and queues initial message.

    Args:
        deal: The DetectedDeal to negotiate
        db: Database session

    Returns:
        Created Negotiation or None if failed
    """
    try:
        # Check if negotiation already exists
        existing = await db.execute(
            select(Negotiation).where(Negotiation.deal_id == deal.id)
        )
        if existing.scalar_one_or_none():
            logger.debug(f"Negotiation already exists for deal {deal.id}")
            return None

        # Get seller info from sell order
        sell_order = deal.sell_order
        if not sell_order:
            logger.warning(f"Deal {deal.id} has no sell order")
            return None

        seller_chat_id = sell_order.chat_id
        seller_sender_id = sell_order.sender_id

        if not seller_chat_id:
            logger.warning(f"Deal {deal.id} sell order has no chat_id")
            return None

        # Create negotiation
        negotiation = Negotiation(
            deal_id=deal.id,
            stage=NegotiationStage.INITIAL,
            seller_chat_id=seller_chat_id,
            seller_sender_id=seller_sender_id,
        )
        db.add(negotiation)
        await db.flush()

        # Generate initial message
        initial_message = generate_response('initial', deal.product)

        # Save message to history
        msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.AI,
            content=initial_message,
        )
        db.add(msg)

        # Queue message for sending
        outbox = OutboxMessage(
            recipient_id=seller_sender_id or seller_chat_id,
            message_text=initial_message,
            status=OutboxStatus.PENDING,
            negotiation_id=negotiation.id,
        )
        db.add(outbox)

        # Update deal status
        deal.status = DealStatus.IN_PROGRESS

        await db.commit()

        logger.info(f"Initiated negotiation for deal {deal.id}, message queued")
        return negotiation

    except Exception as e:
        logger.error(f"Failed to initiate negotiation for deal {deal.id}: {e}")
        await db.rollback()
        return None


async def process_seller_response(
    negotiation: Negotiation,
    response_text: str,
    db: AsyncSession,
) -> bool:
    """
    Process seller's response and generate AI reply.

    Args:
        negotiation: The Negotiation record
        response_text: Seller's message text
        db: Database session

    Returns:
        True if response processed, False otherwise
    """
    try:
        # Save seller's message
        seller_msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.SELLER,
            content=response_text,
        )
        db.add(seller_msg)

        # Analyze response
        sentiment = analyze_response(response_text)
        logger.info(f"Negotiation {negotiation.id}: seller response sentiment = {sentiment}")

        deal = negotiation.deal

        if sentiment == 'negative':
            # Seller not interested - mark deal as lost
            deal.status = DealStatus.LOST
            deal.ai_resolution = f"Продавец отказал: {response_text[:100]}"
            negotiation.stage = NegotiationStage.CLOSED
            await db.commit()
            logger.info(f"Deal {deal.id} marked as LOST")
            return True

        # Check if deal should become warm (after 2+ positive exchanges)
        msg_count = await db.scalar(
            select(NegotiationMessage)
            .where(NegotiationMessage.negotiation_id == negotiation.id)
            .where(NegotiationMessage.role == MessageRole.SELLER)
        )

        if sentiment in ['positive', 'price'] and negotiation.stage != NegotiationStage.INITIAL:
            # Seller engaged - mark as warm for human takeover
            deal.status = DealStatus.WARM
            deal.ai_insight = f"Продавец заинтересован. Последний ответ: {response_text[:100]}"
            negotiation.stage = NegotiationStage.NEGOTIATING
            await db.commit()
            logger.info(f"Deal {deal.id} marked as WARM - ready for manager")
            return True

        # Generate and queue follow-up message
        follow_up = generate_response(sentiment, deal.product, response_text)

        ai_msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.AI,
            content=follow_up,
        )
        db.add(ai_msg)

        outbox = OutboxMessage(
            recipient_id=negotiation.seller_sender_id or negotiation.seller_chat_id,
            message_text=follow_up,
            status=OutboxStatus.PENDING,
            negotiation_id=negotiation.id,
        )
        db.add(outbox)

        # Update negotiation stage
        if negotiation.stage == NegotiationStage.INITIAL:
            negotiation.stage = NegotiationStage.CONTACTED

        await db.commit()
        logger.info(f"Queued follow-up for negotiation {negotiation.id}")
        return True

    except Exception as e:
        logger.error(f"Failed to process response for negotiation {negotiation.id}: {e}")
        await db.rollback()
        return False


async def process_cold_deals(db: AsyncSession) -> int:
    """
    Find cold deals and initiate negotiations.
    Called periodically by scheduler.

    Returns:
        Number of negotiations initiated
    """
    # Find cold deals without negotiations
    result = await db.execute(
        select(DetectedDeal)
        .where(DetectedDeal.status == DealStatus.COLD)
        .limit(10)
    )
    cold_deals = result.scalars().all()

    initiated = 0
    for deal in cold_deals:
        negotiation = await initiate_negotiation(deal, db)
        if negotiation:
            initiated += 1

    if initiated > 0:
        logger.info(f"Initiated {initiated} new negotiations")

    return initiated
