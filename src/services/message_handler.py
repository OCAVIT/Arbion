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
    # iPhone с полной моделью: iPhone 15 Pro Max, iPhone 14, etc.
    r'(iphone\s*\d+\s*(?:pro\s*max|pro|max|plus)?)',
    r'(айфон\s*\d+\s*(?:про\s*макс|про|макс|плюс)?)',
    # Samsung Galaxy
    r'(samsung\s*(?:galaxy\s*)?[sa]\d+\s*(?:fe\s*)?(?:ultra|plus|\+)?)',
    r'(самсунг\s*(?:галакси\s*)?[sa]\d+\s*(?:fe\s*)?(?:ультра|плюс)?)',
    # MacBook
    r'(macbook\s*(?:air|pro)?\s*(?:m\d)?(?:\s*\d+)?)',
    r'(макбук\s*(?:эйр|про)?\s*(?:м\d)?(?:\s*\d+)?)',
    # iPad
    r'(ipad\s*(?:air|pro|mini)?\s*(?:\d+)?)',
    r'(айпад\s*(?:эйр|про|мини)?\s*(?:\d+)?)',
    # AirPods
    r'(airpods\s*(?:pro|max)?\s*(?:\d+)?)',
    r'(эйрподс?\s*(?:про|макс)?\s*(?:\d+)?)',
    # Gaming consoles
    r'(playstation\s*\d+|ps\s*\d+)',
    r'(плейстейшн\s*\d+|пс\s*\d+)',
    r'(xbox\s*(?:series\s*)?[xs]?)',
    r'(nintendo\s*switch(?:\s*lite|oled)?)',
    # Watches
    r'(apple\s*watch\s*(?:se|ultra)?\s*(?:series\s*)?\d*)',
    r'(эпл\s*вотч\s*(?:се|ультра)?\s*(?:серия\s*)?\d*)',
    # Другая электроника
    r'(dyson\s*\w+)',
    r'(дайсон\s*\w+)',
]

# Price patterns - more specific to avoid matching model numbers
PRICE_PATTERNS = [
    # Explicit price markers: "цена 100к", "за 50 тыс", "стоит 30000"
    r'(?:цена|за|стоит|стоимость|прошу|отдам за|продам за|продаю за|хочу)[:\s]*(\d[\d\s]*(?:[.,]\d+)?)\s*(?:т\.?р\.?|тыс\.?|к|руб|р|₽|\$)?',
    # Shorthand with multiplier: "100к", "50 тыс", "30т.р.", "100 к" (разрешаем пробел перед к)
    r'(\d[\d\s]*(?:[.,]\d+)?)\s*(?:т\.?р\.?|тыс\.?|тысяч|к)(?:\b|[,.\s]|$)',
    # Full rubles: "30000 руб", "50000₽", "100000р"
    r'(\d{4,}[\d\s]*(?:[.,]\d+)?)\s*(?:руб\.?|р\.?|₽)',
    # Standalone large number (5-7 digits): likely a price
    r'(?:^|[^\d])(\d{5,7})(?:[^\d]|$)',
    # Number followed by "рублей": "50000 рублей"
    r'(\d[\d\s]*(?:[.,]\d+)?)\s*рубл',
]

# Phone number patterns to detect warm deals
PHONE_PATTERNS = [
    r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 (999) 123-45-67
    r'\+?[78]\d{10}',  # +79991234567
    r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b',  # 999-123-45-67
]

# Region patterns - expanded list with common abbreviations
REGIONS = [
    'москва', 'мск', 'moscow', 'мос',
    'питер', 'спб', 'санкт-петербург', 'петербург', 'ленинград',
    'новосибирск', 'нск', 'новосиб',
    'екатеринбург', 'екб', 'екат',
    'казань', 'кзн',
    'нижний новгород', 'нн', 'нижний',
    'челябинск', 'чел', 'челяба',
    'самара', 'смр',
    'омск',
    'ростов', 'ростов-на-дону', 'рнд', 'ростов на дону',
    'уфа',
    'красноярск', 'крск',
    'пермь',
    'воронеж', 'врн',
    'волгоград', 'влг',
    'краснодар', 'крд',
    'саратов',
    'тюмень',
    'тольятти',
    'ижевск',
    'барнаул',
    'ульяновск',
    'иркутск',
    'хабаровск',
    'ярославль',
    'владивосток', 'влад',
    'махачкала',
    'томск',
    'оренбург',
    'кемерово',
    'новокузнецк',
    'рязань',
    'калининград', 'клгд',
    'сочи',
    'астрахань',
    'пенза',
    'липецк',
    'тула',
    'киров',
    'чебоксары',
    'курск',
    'ставрополь',
    'улан-удэ',
    'тверь',
    'брянск',
    'белгород',
    'сургут',
    'вологда',
    'владимир',
    'архангельск',
    'смоленск',
    'калуга',
    'орёл', 'орел',
    'мурманск',
    'подольск',
    'бийск',
    'прокопьевск',
    'балашиха',
    'рыбинск',
    'северодвинск',
    'армавир',
    'балаково',
    'королёв', 'королев',
    'химки',
    'мытищи',
    'люберцы',
    'одинцово',
    'подмосковье', 'мо',
]

# Normalize region names
REGION_NORMALIZE = {
    'мск': 'Москва',
    'москва': 'Москва',
    'moscow': 'Москва',
    'мос': 'Москва',
    'спб': 'Санкт-Петербург',
    'питер': 'Санкт-Петербург',
    'санкт-петербург': 'Санкт-Петербург',
    'петербург': 'Санкт-Петербург',
    'ленинград': 'Санкт-Петербург',
    'нск': 'Новосибирск',
    'новосиб': 'Новосибирск',
    'екб': 'Екатеринбург',
    'екат': 'Екатеринбург',
    'кзн': 'Казань',
    'нн': 'Нижний Новгород',
    'нижний': 'Нижний Новгород',
    'чел': 'Челябинск',
    'челяба': 'Челябинск',
    'смр': 'Самара',
    'рнд': 'Ростов-на-Дону',
    'ростов': 'Ростов-на-Дону',
    'ростов на дону': 'Ростов-на-Дону',
    'ростов-на-дону': 'Ростов-на-Дону',
    'крск': 'Красноярск',
    'врн': 'Воронеж',
    'влг': 'Волгоград',
    'крд': 'Краснодар',
    'влад': 'Владивосток',
    'клгд': 'Калининград',
    'орёл': 'Орёл',
    'орел': 'Орёл',
    'королёв': 'Королёв',
    'королев': 'Королёв',
    'мо': 'Московская область',
    'подмосковье': 'Московская область',
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
    Извлечение названия товара из текста.
    Использует известные паттерны, затем fallback на текст после ключевого слова.
    """
    text_lower = text.lower()

    # Сначала пробуем известные паттерны продуктов
    for pattern in PRODUCT_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            product = match.group(1).strip()
            # Правильная капитализация для брендов
            product = normalize_product_name(product)
            return product

    # Fallback: извлекаем текст после ключевого слова купли/продажи
    all_keywords = BUY_KEYWORDS + SELL_KEYWORDS
    for keyword in all_keywords:
        if keyword in text_lower:
            idx = text_lower.find(keyword)
            after_keyword = text[idx + len(keyword):].strip()
            # Берём текст до запятой, переноса строки или цены
            chunk = re.split(r'[,\n]|(?:\d+\s*(?:т\.?р|тыс|к|руб|р|₽))', after_keyword)[0].strip()
            if chunk and len(chunk) > 2:
                # Очистка
                chunk = re.sub(r'^[!.\s]+', '', chunk)
                chunk = chunk[:100]  # Ограничение длины
                return chunk if chunk else "Товар"

    return "Товар"


def normalize_product_name(product: str) -> str:
    """
    Нормализация названия продукта с правильной капитализацией брендов.
    """
    # Сначала применяем title() для базовой капитализации
    product = product.title()

    # Исправляем известные бренды
    replacements = {
        'Iphone': 'iPhone',
        'Ipad': 'iPad',
        'Macbook': 'MacBook',
        'Airpods': 'AirPods',
        'Airpod': 'AirPod',
        'Imac': 'iMac',
        'Ipod': 'iPod',
        'Apple Watch': 'Apple Watch',
        'Samsung': 'Samsung',
        'Galaxy': 'Galaxy',
        'Playstation': 'PlayStation',
        'Xbox': 'Xbox',
        'Nintendo': 'Nintendo',
        'Dyson': 'Dyson',
        ' Pro Max': ' Pro Max',
        ' Pro ': ' Pro ',
        ' Max': ' Max',
        ' Plus': ' Plus',
        ' Ultra': ' Ultra',
        ' Air': ' Air',
        ' Mini': ' Mini',
        ' Se': ' SE',
    }

    for old, new in replacements.items():
        product = product.replace(old, new)

    return product


def extract_price(text: str) -> Optional[Decimal]:
    """
    Извлечение цены из текста сообщения.
    Обрабатывает форматы: 100к, 100 тыс, 100000 руб, цена 100к
    """
    text_lower = text.lower()

    # Собираем все найденные цены
    found_prices = []

    for pattern in PRICE_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            try:
                price_str = match.group(1).replace(' ', '').replace(',', '.')
                price = Decimal(price_str)

                # Проверяем множитель 'к' или 'тыс'
                full_match = match.group(0).lower()
                if any(m in full_match for m in ['к', 'тыс', 'т.р', 'тр']):
                    price *= 1000

                # Проверка диапазона - цены обычно от 1000 до 10000000
                if 1000 <= price <= 10000000:
                    found_prices.append(price)
            except Exception:
                pass

    # Возвращаем наиболее вероятную цену (предпочитаем среднюю)
    if found_prices:
        # Если найдено несколько цен, берём первую (обычно основная цена)
        return found_prices[0]

    return None


def extract_phone(text: str) -> Optional[str]:
    """
    Извлечение номера телефона из текста.
    Возвращает найденный номер или None.
    """
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            phone = match.group(0)
            # Нормализация - оставляем только цифры
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 10:
                return phone
    return None


def extract_region(text: str) -> Optional[str]:
    """
    Извлечение региона/города из текста сообщения.
    Поддерживает сокращения и разные варианты написания.
    """
    text_lower = text.lower()

    # Сначала ищем точные совпадения для сокращений
    for region in REGIONS:
        # Для коротких сокращений используем границы слов
        if len(region) <= 3:
            if re.search(rf'\b{re.escape(region)}\b', text_lower):
                return REGION_NORMALIZE.get(region, region.title())
        else:
            if region in text_lower:
                return REGION_NORMALIZE.get(region, region.title())

    return None


# Quantity patterns
QUANTITY_PATTERNS = [
    r'(\d+)\s*(?:шт\.?|штук[иа]?|единиц[аы]?|ед\.?)',
    r'(?:количество|кол-во|кол\.?)\s*[:\-]?\s*(\d+)',
]


def extract_quantity(text: str) -> Optional[str]:
    """Извлечение количества из текста. Возвращает строку вида '5 шт' или None."""
    text_lower = text.lower()
    for pattern in QUANTITY_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            qty = match.group(1) or match.group(2)
            if qty and int(qty) > 0:
                return f"{qty} шт"
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
    Проверка, является ли сообщение ответом на активные переговоры.
    Если да - обрабатывает через AI negotiator.

    Args:
        db: Database session
        sender_id: Telegram sender ID
        message_text: Message text

    Returns:
        True if message was a negotiation response
    """
    if not sender_id:
        logger.info(f"check_negotiation_response: sender_id пустой, пропускаем")
        return False

    try:
        logger.info(f">>> check_negotiation_response: sender_id={sender_id}, текст: '{message_text[:50]}...'")

        # Проверяем, является ли это ответом ПРОДАВЦА (берём самые свежие переговоры)
        seller_query = (
            select(Negotiation)
            .options(selectinload(Negotiation.deal))
            .where(
                and_(
                    or_(
                        Negotiation.seller_sender_id == sender_id,
                        Negotiation.seller_chat_id == sender_id,
                    ),
                    Negotiation.stage != NegotiationStage.CLOSED,
                )
            )
            .order_by(Negotiation.id.desc())
            .limit(1)
        )
        result = await db.execute(seller_query)
        negotiation = result.scalar_one_or_none()

        if negotiation:
            logger.info(
                f">>> НАЙДЕНЫ переговоры #{negotiation.id} для продавца {sender_id} "
                f"(stage={negotiation.stage.value}, deal_id={negotiation.deal_id})"
            )
            success = await process_seller_response(negotiation, message_text, db)
            logger.info(f">>> process_seller_response вернул: {success}")
            return True

        logger.info(f">>> Переговоры для продавца sender_id={sender_id} НЕ найдены, проверяем покупателя...")

        # Проверяем, является ли это ответом ПОКУПАТЕЛЯ (берём самые свежие переговоры)
        buyer_query = (
            select(Negotiation)
            .options(selectinload(Negotiation.deal))
            .join(DetectedDeal, Negotiation.deal_id == DetectedDeal.id)
            .where(
                and_(
                    or_(
                        DetectedDeal.buyer_sender_id == sender_id,
                        DetectedDeal.buyer_chat_id == sender_id,
                    ),
                    Negotiation.stage != NegotiationStage.CLOSED,
                )
            )
            .order_by(Negotiation.id.desc())
            .limit(1)
        )
        result = await db.execute(buyer_query)
        negotiation = result.scalar_one_or_none()

        if negotiation:
            logger.info(
                f">>> НАЙДЕНЫ переговоры #{negotiation.id} для покупателя {sender_id} "
                f"(stage={negotiation.stage.value}, deal_id={negotiation.deal_id})"
            )
            success = await process_buyer_response(negotiation, message_text, db)
            logger.info(f">>> process_buyer_response вернул: {success}")
            return True

        logger.info(f">>> Активные переговоры для sender_id={sender_id} не найдены")
        return False

    except Exception as e:
        # Если ошибка с enum или БД - логируем ERROR и возвращаем False
        logger.error(f"!!! ОШИБКА при проверке переговоров для sender_id={sender_id}: {e}", exc_info=True)
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

        logger.info(f"New message from {chat_title} (chat_id={chat_id}, sender_id={sender_id}): {raw_text[:50]}...")

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
            logger.info(f">>> Raw message сохранено, sender_id={sender_id}")

            # ВАЖНО: Сначала проверяем, является ли сообщение ответом на активные переговоры
            # Это критично, т.к. ответ "да, продаю" содержит ключевое слово и иначе
            # обработается как новая заявка вместо ответа на переговоры
            is_negotiation_response = False
            try:
                is_negotiation_response = await check_negotiation_response(db, sender_id, raw_text)
                logger.info(f">>> check_negotiation_response вернул: {is_negotiation_response}")
            except Exception as neg_check_error:
                logger.error(f"!!! Ошибка в check_negotiation_response: {neg_check_error}", exc_info=True)
                # Продолжаем обработку как обычное сообщение

            if not is_negotiation_response:
                # Если это не ответ на переговоры - проверяем, является ли это новой заявкой
                order_type = detect_order_type(raw_text)

                if order_type:
                    # Извлекаем товар, цену и регион
                    product = extract_product(raw_text)
                    price = extract_price(raw_text)
                    region = extract_region(raw_text)

                    logger.info(f"Parsed: type={order_type.value}, product={product}, price={price}, region={region}")

                    # Проверяем, существует ли уже такая заявка
                    existing = await db.execute(
                        select(Order).where(
                            Order.chat_id == chat_id,
                            Order.message_id == message_id,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        # Создаём заявку
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
                        await db.flush()  # Получаем ID заявки

                        logger.info(
                            f"Created {order_type.value} order #{order.id}: {product} "
                            f"(price: {price}, region: {region})"
                        )

                        # Пытаемся найти совпадение с противоположными заявками
                        deal = await try_match_orders(db, order)
                        if deal:
                            logger.info(f"Auto-matched into deal #{deal.id}")
                            # Запускаем AI переговоры для новой сделки
                            try:
                                logger.info(f"Запускаем initiate_negotiation для сделки #{deal.id}")
                                negotiation = await initiate_negotiation(deal, db)
                                if negotiation:
                                    logger.info(f"Переговоры #{negotiation.id} созданы успешно")
                                else:
                                    logger.warning(f"initiate_negotiation вернул None для сделки #{deal.id}")
                            except Exception as neg_error:
                                logger.error(f"Ошибка при создании переговоров: {neg_error}", exc_info=True)

            # Отмечаем сырое сообщение как обработанное
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
            logger.info(f">>> Транзакция закоммичена успешно для сообщения от sender_id={sender_id}")

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
