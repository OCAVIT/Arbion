"""
AI Negotiator service для прогрева холодных лидов.

Функции:
- Отправка первичных сообщений продавцам и покупателям
- Обработка ответов с хранением контекста
- Умное ведение диалога до получения номера телефона
- Прогресс сделок: COLD -> IN_PROGRESS -> WARM
"""

import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.models import (
    DealStatus,
    DetectedDeal,
    MessageRole,
    MessageTarget,
    Negotiation,
    NegotiationMessage,
    NegotiationStage,
    Order,
    OutboxMessage,
    OutboxStatus,
)

logger = logging.getLogger(__name__)

# =====================================================
# ШАБЛОНЫ СООБЩЕНИЙ
# =====================================================

# Первичное сообщение продавцу
INITIAL_SELLER_TEMPLATES = [
    "привет, {product} ещё есть?",
    "здравствуйте, {product} актуально?",
    "добрый день, {product} продаёте ещё?",
    "привет! по {product} - актуально?",
    "здравствуйте, интересует {product}, ещё в продаже?",
    "добрый день! {product} ещё есть?",
    "привет, по поводу {product} - ещё актуально?",
]

# Первичное сообщение покупателю
INITIAL_BUYER_TEMPLATES = [
    "привет, нашёл {product} по твоему запросу, интересно?",
    "здравствуйте, есть {product} - актуально для вас?",
    "добрый день! по вашему запросу - есть {product}, интересует?",
    "привет! нашёл {product}, ещё ищете?",
    "здравствуйте, {product} в наличии - подойдёт?",
]

# Ответы на положительную реакцию (первый ответ)
FOLLOWUP_POSITIVE_FIRST = [
    "отлично! а состояние какое? есть косяки?",
    "супер, что по состоянию скажешь?",
    "хорошо, а по состоянию как? царапины, сколы есть?",
    "понял, расскажи про состояние - важно чтобы всё работало",
    "ок, а комплект полный? коробка есть?",
]

# Уточнение цены
FOLLOWUP_PRICE = [
    "понял, а по цене можно подвинуться немного?",
    "ясно, если скинешь чуть-чуть - сразу заберу",
    "а торг будет? могу подъехать сегодня",
    "а если чуть дешевле - возьму сейчас",
    "по цене договоримся? заберу быстро",
]

# Уточнение состояния (второй этап)
FOLLOWUP_CONDITION = [
    "понял, а аккумулятор как держит?",
    "ясно, а экран без трещин? битых пикселей нет?",
    "хорошо, а всё работает? камера, звук?",
    "ок, а зарядка родная? кабель есть?",
]

# Запрос контакта (финальный этап)
FOLLOWUP_ASK_CONTACT = [
    "отлично, давай созвонимся - скинь номер",
    "хорошо, тогда давай номер телефона - обсудим детали",
    "понял, скинь номер - наберу сегодня",
    "ок, давай контакт для связи - телефон или телега",
    "договорились, скинь номер - свяжусь в течение часа",
    "супер, давай номер телефона чтоб созвониться",
]

# Уточнение если непонятно
FOLLOWUP_UNCLEAR = [
    "не совсем понял, так продаёшь ещё?",
    "можно подробнее? интересует покупка",
    "так актуально или нет?",
    "прости, не понял - в продаже ещё?",
]

# Ответ на негатив (прощание)
GOODBYE_TEMPLATES = [
    "понял, спасибо",
    "ок, если что - пиши",
    "понял, удачи с продажей",
]

# Паттерны для определения номера телефона
PHONE_PATTERNS = [
    r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    r'\+?[78]\d{10}',
    r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b',
]

# Ключевые слова
POSITIVE_KEYWORDS = [
    'да', 'актуально', 'есть', 'продаю', 'готов', 'можно',
    'конечно', 'пишите', 'звоните', 'в наличии', 'ок', 'ok',
    'давай', 'норм', 'хорошо', 'отлично', 'пойдёт', 'идёт',
    'работает', 'всё ок', 'могу', 'да конечно', 'угу',
]

NEGATIVE_KEYWORDS = [
    'нет', 'продано', 'неактуально', 'не продаю', 'забронировано',
    'уже нет', 'sold', 'занято', 'отдал', 'продал', 'не актуально',
    'извини', 'к сожалению', 'уже забрали',
]

PRICE_KEYWORDS = [
    'цена', 'стоит', 'рублей', 'тысяч', 'руб', '₽', 'торг',
    'тыс', 'тр', 'к ', ' к', 'рубл', 'прошу', 'отдам за',
]

CONDITION_KEYWORDS = [
    'состояние', 'царапины', 'сколы', 'работает', 'новый', 'бу',
    'идеал', 'норм', 'хорошее', 'отличное', 'без косяков',
    'комплект', 'коробка', 'зарядка', 'аккумулятор', 'экран',
]

CONTACT_KEYWORDS = [
    'телефон', 'номер', 'звони', 'набери', 'позвони', 'контакт',
    'вот номер', 'мой номер', 'телега', 'ватсап', 'whatsapp',
    'telegram', 'тг', 'вайбер', 'viber',
]


# =====================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================

def extract_phone_from_text(text: str) -> Optional[str]:
    """Извлечение номера телефона из текста."""
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            phone = match.group(0)
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                return phone
    return None


def analyze_response(text: str) -> Tuple[str, Optional[str]]:
    """
    Анализ ответа продавца/покупателя.

    Returns:
        Tuple[sentiment, phone]:
        - sentiment: 'positive', 'negative', 'price', 'condition', 'contact', 'unclear'
        - phone: найденный номер телефона или None
    """
    text_lower = text.lower()

    # Сначала проверяем на наличие телефона
    phone = extract_phone_from_text(text)
    if phone:
        return 'contact', phone

    # Проверка на упоминание контакта (без номера)
    for keyword in CONTACT_KEYWORDS:
        if keyword in text_lower:
            return 'contact', None

    # Проверка на негатив
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in text_lower:
            return 'negative', None

    # Проверка на обсуждение цены
    for keyword in PRICE_KEYWORDS:
        if keyword in text_lower:
            return 'price', None

    # Проверка на обсуждение состояния
    for keyword in CONDITION_KEYWORDS:
        if keyword in text_lower:
            return 'condition', None

    # Проверка на позитив
    for keyword in POSITIVE_KEYWORDS:
        if keyword in text_lower:
            return 'positive', None

    return 'unclear', None


async def get_conversation_context(
    negotiation: Negotiation,
    db: AsyncSession,
    target: MessageTarget = MessageTarget.SELLER
) -> List[dict]:
    """
    Получение истории разговора для контекста.

    Returns:
        Список сообщений в формате [{'role': 'ai'|'seller'|'buyer', 'content': '...'}]
    """
    result = await db.execute(
        select(NegotiationMessage)
        .where(NegotiationMessage.negotiation_id == negotiation.id)
        .where(NegotiationMessage.target == target)
        .order_by(NegotiationMessage.created_at)
    )
    messages = result.scalars().all()

    context = []
    for msg in messages:
        context.append({
            'role': msg.role.value,
            'content': msg.content,
        })

    return context


def count_exchanges(context: List[dict]) -> int:
    """Подсчёт количества обменов сообщениями (пара AI + ответ)."""
    ai_count = sum(1 for m in context if m['role'] == 'ai')
    other_count = sum(1 for m in context if m['role'] in ['seller', 'buyer'])
    return min(ai_count, other_count)


def determine_next_action(
    sentiment: str,
    phone: Optional[str],
    context: List[dict],
    stage: NegotiationStage
) -> Tuple[str, Optional[str]]:
    """
    Определение следующего действия на основе анализа.

    Returns:
        Tuple[action, response]:
        - action: 'respond', 'warm', 'close'
        - response: текст ответа или None
    """
    exchanges = count_exchanges(context)

    # Если получили номер телефона - сделка тёплая!
    if phone:
        return 'warm', None

    # Негатив - закрываем
    if sentiment == 'negative':
        return 'close', random.choice(GOODBYE_TEMPLATES)

    # Логика в зависимости от количества обменов
    if exchanges == 0:
        # Первый ответ - уточняем состояние
        if sentiment in ['positive', 'price', 'condition']:
            return 'respond', random.choice(FOLLOWUP_POSITIVE_FIRST)
        elif sentiment == 'contact':
            # Упоминают контакт, но номера нет - просим
            return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)
        else:
            return 'respond', random.choice(FOLLOWUP_UNCLEAR)

    elif exchanges == 1:
        # Второй обмен - обсуждаем цену или состояние
        if sentiment == 'price':
            return 'respond', random.choice(FOLLOWUP_PRICE)
        elif sentiment in ['positive', 'condition']:
            return 'respond', random.choice(FOLLOWUP_CONDITION)
        elif sentiment == 'contact':
            return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)
        else:
            return 'respond', random.choice(FOLLOWUP_UNCLEAR)

    elif exchanges >= 2:
        # Третий+ обмен - пора просить контакт
        if sentiment == 'contact':
            # Упоминают контакт но номера нет - уточняем
            return 'respond', "скинь номер телефона - созвонимся"
        elif sentiment in ['positive', 'price', 'condition']:
            return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)
        else:
            return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)

    return 'respond', random.choice(FOLLOWUP_UNCLEAR)


def generate_response(stage: str, product: str, context: str = "") -> str:
    """
    Генерация ответа на основе стадии.
    Для совместимости со старым кодом.
    """
    product_lower = product.lower() if product else "товар"

    if stage == 'initial' or stage == 'initial_seller':
        template = random.choice(INITIAL_SELLER_TEMPLATES)
        return template.format(product=product_lower)

    elif stage == 'initial_buyer':
        template = random.choice(INITIAL_BUYER_TEMPLATES)
        return template.format(product=product_lower)

    elif stage == 'positive':
        return random.choice(FOLLOWUP_POSITIVE_FIRST)

    elif stage == 'price':
        return random.choice(FOLLOWUP_PRICE)

    elif stage == 'condition':
        return random.choice(FOLLOWUP_CONDITION)

    elif stage == 'contact':
        return random.choice(FOLLOWUP_ASK_CONTACT)

    elif stage == 'unclear':
        return random.choice(FOLLOWUP_UNCLEAR)

    else:
        return "Подскажите подробнее, пожалуйста."


# =====================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =====================================================

async def initiate_negotiation(deal: DetectedDeal, db: AsyncSession) -> Optional[Negotiation]:
    """
    Начало переговоров по холодной сделке.
    Создаёт Negotiation и отправляет первые сообщения продавцу и покупателю.
    """
    try:
        # Проверяем, нет ли уже переговоров
        existing = await db.execute(
            select(Negotiation).where(Negotiation.deal_id == deal.id)
        )
        if existing.scalar_one_or_none():
            logger.debug(f"Переговоры для сделки {deal.id} уже существуют")
            return None

        # Получаем данные продавца из sell_order
        sell_order = deal.sell_order
        if not sell_order:
            result = await db.execute(
                select(Order).where(Order.id == deal.sell_order_id)
            )
            sell_order = result.scalar_one_or_none()
            if not sell_order:
                logger.warning(f"Сделка {deal.id} не имеет sell_order (id={deal.sell_order_id})")
                return None

        seller_chat_id = sell_order.chat_id
        seller_sender_id = sell_order.sender_id

        if not seller_chat_id:
            logger.warning(f"Сделка {deal.id}: sell_order без chat_id")
            return None

        # Создаём переговоры
        negotiation = Negotiation(
            deal_id=deal.id,
            stage=NegotiationStage.INITIAL,
            seller_chat_id=seller_chat_id,
            seller_sender_id=seller_sender_id,
        )
        db.add(negotiation)
        await db.flush()

        logger.info(
            f"Созданы переговоры #{negotiation.id} для сделки #{deal.id}: "
            f"seller_sender_id={seller_sender_id}, seller_chat_id={seller_chat_id}, "
            f"buyer_sender_id={deal.buyer_sender_id}, buyer_chat_id={deal.buyer_chat_id}"
        )

        # Генерируем первое сообщение продавцу
        seller_message = generate_response('initial_seller', deal.product)

        # Сохраняем в историю (чат с продавцом)
        msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.AI,
            target=MessageTarget.SELLER,
            content=seller_message,
        )
        db.add(msg)

        # Добавляем в очередь отправки
        outbox_seller = OutboxMessage(
            recipient_id=seller_sender_id or seller_chat_id,
            message_text=seller_message,
            status=OutboxStatus.PENDING,
            negotiation_id=negotiation.id,
        )
        db.add(outbox_seller)

        # Также контактируем покупателя
        buyer_sender_id = deal.buyer_sender_id
        buyer_chat_id = deal.buyer_chat_id

        if buyer_sender_id or buyer_chat_id:
            buyer_message = generate_response('initial_buyer', deal.product)

            # Сохраняем в историю (чат с покупателем)
            buyer_msg = NegotiationMessage(
                negotiation_id=negotiation.id,
                role=MessageRole.AI,
                target=MessageTarget.BUYER,
                content=buyer_message,
            )
            db.add(buyer_msg)

            # Добавляем в очередь отправки
            outbox_buyer = OutboxMessage(
                recipient_id=buyer_sender_id or buyer_chat_id,
                message_text=buyer_message,
                status=OutboxStatus.PENDING,
                negotiation_id=negotiation.id,
            )
            db.add(outbox_buyer)
            logger.info(f"Сделка {deal.id}: сообщения отправлены продавцу и покупателю")
        else:
            logger.info(f"Сделка {deal.id}: сообщение отправлено только продавцу (нет контакта покупателя)")

        # Обновляем статус сделки
        deal.status = DealStatus.IN_PROGRESS

        return negotiation

    except Exception as e:
        logger.error(f"Ошибка при создании переговоров для сделки {deal.id}: {e}")
        raise


async def process_seller_response(
    negotiation: Negotiation,
    response_text: str,
    db: AsyncSession,
) -> bool:
    """
    Обработка ответа продавца с умной логикой ведения диалога.

    ВАЖНО: Эта функция НЕ делает commit - это обязанность вызывающего кода.
    """
    try:
        logger.info(
            f">>> process_seller_response: переговоры #{negotiation.id}, "
            f"текст: '{response_text[:50]}...', stage={negotiation.stage.value}"
        )

        # Сохраняем сообщение продавца
        seller_msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.SELLER,
            target=MessageTarget.SELLER,
            content=response_text,
        )
        db.add(seller_msg)
        await db.flush()
        logger.info(f">>> Сообщение продавца #{seller_msg.id} сохранено (negotiation_id={negotiation.id})")

        # Получаем контекст разговора
        context = await get_conversation_context(negotiation, db, MessageTarget.SELLER)

        # Анализируем ответ
        sentiment, phone = analyze_response(response_text)
        logger.info(f"Переговоры {negotiation.id}: sentiment={sentiment}, phone={phone}")

        deal = negotiation.deal

        # Определяем следующее действие
        action, response = determine_next_action(sentiment, phone, context, negotiation.stage)

        logger.info(f"Переговоры {negotiation.id}: action={action}, response='{response[:30] if response else None}...'")

        if action == 'warm':
            # Сделка тёплая - получили номер телефона!
            deal.status = DealStatus.WARM
            deal.ai_insight = f"Продавец заинтересован. Получен контакт: {phone or 'упомянут'}. Последнее сообщение: {response_text[:100]}"
            negotiation.stage = NegotiationStage.WARM
            await db.flush()
            logger.info(f">>> Сделка {deal.id} стала WARM - получен номер телефона!")
            return True

        elif action == 'close':
            # Продавец не заинтересован
            deal.status = DealStatus.LOST
            deal.ai_resolution = f"Продавец отказал: {response_text[:100]}"
            negotiation.stage = NegotiationStage.CLOSED

            # Отправляем прощальное сообщение
            if response:
                goodbye_msg = NegotiationMessage(
                    negotiation_id=negotiation.id,
                    role=MessageRole.AI,
                    target=MessageTarget.SELLER,
                    content=response,
                )
                db.add(goodbye_msg)

                outbox = OutboxMessage(
                    recipient_id=negotiation.seller_sender_id or negotiation.seller_chat_id,
                    message_text=response,
                    status=OutboxStatus.PENDING,
                    negotiation_id=negotiation.id,
                )
                db.add(outbox)

            await db.flush()
            logger.info(f">>> Сделка {deal.id} закрыта как LOST")
            return True

        elif action == 'respond' and response:
            # Продолжаем диалог
            ai_msg = NegotiationMessage(
                negotiation_id=negotiation.id,
                role=MessageRole.AI,
                target=MessageTarget.SELLER,
                content=response,
            )
            db.add(ai_msg)
            logger.info(f">>> Создано AI сообщение для продавца: '{response[:30]}...'")

            outbox = OutboxMessage(
                recipient_id=negotiation.seller_sender_id or negotiation.seller_chat_id,
                message_text=response,
                status=OutboxStatus.PENDING,
                negotiation_id=negotiation.id,
            )
            db.add(outbox)
            logger.info(f">>> Создано outbox сообщение для recipient_id={negotiation.seller_sender_id or negotiation.seller_chat_id}")

            # Обновляем стадию переговоров
            if negotiation.stage == NegotiationStage.INITIAL:
                negotiation.stage = NegotiationStage.CONTACTED
            elif negotiation.stage == NegotiationStage.CONTACTED:
                negotiation.stage = NegotiationStage.NEGOTIATING

            # Обновляем ai_insight
            exchanges = count_exchanges(context)
            deal.ai_insight = f"В диалоге. Обменов: {exchanges + 1}. Последний ответ: {response_text[:50]}"

            await db.flush()
            logger.info(f">>> Переговоры {negotiation.id}: follow-up добавлен в outbox: '{response}'")
            return True

        # Если ничего не подошло - просто сохраняем
        await db.flush()
        logger.info(f">>> Переговоры {negotiation.id}: сообщение сохранено без ответа AI")
        return True

    except Exception as e:
        logger.error(f"!!! ОШИБКА при обработке ответа продавца для переговоров {negotiation.id}: {e}", exc_info=True)
        raise  # Пробрасываем ошибку для обработки в вызывающем коде


async def process_buyer_response(
    negotiation: Negotiation,
    response_text: str,
    db: AsyncSession,
) -> bool:
    """
    Обработка ответа покупателя.

    ВАЖНО: Эта функция НЕ делает commit - это обязанность вызывающего кода.
    """
    try:
        logger.info(
            f">>> process_buyer_response: переговоры #{negotiation.id}, "
            f"текст: '{response_text[:50]}...', stage={negotiation.stage.value}"
        )

        # Сохраняем сообщение покупателя
        buyer_msg = NegotiationMessage(
            negotiation_id=negotiation.id,
            role=MessageRole.BUYER,
            target=MessageTarget.BUYER,
            content=response_text,
        )
        db.add(buyer_msg)
        await db.flush()
        logger.info(f">>> Сообщение покупателя #{buyer_msg.id} сохранено")

        # Получаем контекст разговора с покупателем
        context = await get_conversation_context(negotiation, db, MessageTarget.BUYER)

        # Анализируем ответ
        sentiment, phone = analyze_response(response_text)
        logger.info(f"Переговоры {negotiation.id} (покупатель): sentiment={sentiment}, phone={phone}")

        deal = negotiation.deal

        # Определяем следующее действие
        action, response = determine_next_action(sentiment, phone, context, negotiation.stage)
        logger.info(f"Переговоры {negotiation.id} (покупатель): action={action}, response='{response[:30] if response else None}...'")

        if action == 'warm' and phone:
            # Покупатель дал номер - отмечаем
            deal.ai_insight = (deal.ai_insight or "") + f"\nПокупатель дал контакт: {phone}"
            await db.flush()
            logger.info(f">>> Сделка {deal.id}: покупатель дал номер!")
            return True

        elif action == 'close':
            # Покупатель отказался
            deal.ai_insight = (deal.ai_insight or "") + f"\nПокупатель отказался: {response_text[:50]}"

            if response:
                goodbye_msg = NegotiationMessage(
                    negotiation_id=negotiation.id,
                    role=MessageRole.AI,
                    target=MessageTarget.BUYER,
                    content=response,
                )
                db.add(goodbye_msg)

                outbox = OutboxMessage(
                    recipient_id=deal.buyer_sender_id or deal.buyer_chat_id,
                    message_text=response,
                    status=OutboxStatus.PENDING,
                    negotiation_id=negotiation.id,
                )
                db.add(outbox)

            await db.flush()
            logger.info(f">>> Сделка {deal.id}: покупатель отказался")
            return True

        elif action == 'respond' and response:
            # Продолжаем диалог с покупателем
            ai_msg = NegotiationMessage(
                negotiation_id=negotiation.id,
                role=MessageRole.AI,
                target=MessageTarget.BUYER,
                content=response,
            )
            db.add(ai_msg)
            logger.info(f">>> Создано AI сообщение для покупателя: '{response[:30]}...'")

            outbox = OutboxMessage(
                recipient_id=deal.buyer_sender_id or deal.buyer_chat_id,
                message_text=response,
                status=OutboxStatus.PENDING,
                negotiation_id=negotiation.id,
            )
            db.add(outbox)
            logger.info(f">>> Создано outbox сообщение для buyer_id={deal.buyer_sender_id or deal.buyer_chat_id}")

            # Обновляем ai_insight
            deal.ai_insight = (deal.ai_insight or "") + f"\nПокупатель: {response_text[:30]}"

            await db.flush()
            logger.info(f">>> Переговоры {negotiation.id}: follow-up покупателю добавлен в outbox: '{response}'")
            return True

        # Просто сохраняем
        deal.ai_insight = (deal.ai_insight or "") + f"\nПокупатель: {response_text[:50]}"
        await db.flush()
        logger.info(f">>> Переговоры {negotiation.id}: сообщение покупателя сохранено без ответа AI")
        return True

    except Exception as e:
        logger.error(f"!!! ОШИБКА при обработке ответа покупателя для переговоров {negotiation.id}: {e}", exc_info=True)
        raise  # Пробрасываем ошибку для обработки в вызывающем коде


async def process_cold_deals(db: AsyncSession) -> int:
    """
    Поиск холодных сделок и инициация переговоров.
    Вызывается периодически планировщиком.
    """
    # Находим холодные сделки без переговоров
    result = await db.execute(
        select(DetectedDeal)
        .where(DetectedDeal.status == DealStatus.COLD)
        .limit(10)
    )
    cold_deals = result.scalars().all()

    initiated = 0
    for deal in cold_deals:
        try:
            negotiation = await initiate_negotiation(deal, db)
            if negotiation:
                initiated += 1
        except Exception as e:
            logger.error(f"Ошибка при инициации переговоров для сделки {deal.id}: {e}")
            await db.rollback()
            continue

    if initiated > 0:
        await db.commit()
        logger.info(f"Инициировано {initiated} новых переговоров")

    return initiated
