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
    DetectedDeal, DealStatus, MessageRole, MessageTarget,
    Negotiation, NegotiationMessage, NegotiationStage,
    Order, OrderType, RawMessage
)
from src.services.ai_negotiator import initiate_negotiation, process_seller_response, process_buyer_response

logger = logging.getLogger(__name__)

# Patterns for detecting buy/sell intent
BUY_KEYWORDS = [
    # Существующие
    "куплю", "покупаю", "ищу", "нужен", "нужна", "нужно", "приму", "возьму",
    # B2B оптовые
    "закупаю", "закупаем", "закупим", "потребность", "заявка на",
    "нужен объём", "нужен объем", "требуется", "готовы купить",
    "готовы взять", "ищем поставщика", "запрос на", "кто продаёт",
    "кто продает", "есть у кого", "предложите", "скиньте цену",
    "актуальная цена", "кто может поставить", "нужна поставка",
]
SELL_KEYWORDS = [
    # Существующие
    "продам", "продаю", "отдам", "есть в наличии", "в наличии", "готов продать",
    # B2B оптовые
    "продаём", "продаем", "реализуем", "реализую", "остатки",
    "сток", "распродажа", "ликвидация склада", "по себестоимости",
    "отгрузка со склада", "отгрузка с завода", "отгрузим", "поставим", "поставляем",
    "предлагаем", "предлагаю", "есть объём", "есть объем",
    "свободный остаток", "наличие на складе", "наличие", "склад москва",
    "склад мск", "с завода", "от производителя", "опт",
]

# Стройматериалы — основная ниша
CONSTRUCTION_PRODUCTS = {
    # Металлопрокат
    r'арматур[аыуе]?\s*[АаAa]?\s*\d*[СсCc]?\d*': 'арматура',
    r'профнастил\w*': 'профнастил',
    r'профлист\w*': 'профлист',
    r'лист\s*(горяче|холодно)?катан\w*': 'лист стальной',
    r'труб[аыуе]?\s*(профильн|круглая|стальн|ВГП|электросварн)?\w*': 'труба',
    r'швеллер\w*': 'швеллер',
    r'двутавр\w*': 'двутавр',
    r'балк[аиу]\w*': 'балка',
    r'угол[оо]?к?\w*\s*(стальн|равнополочн|неравнополочн)?\w*': 'уголок',
    r'кругл?я?к?\w*\s*\d+': 'круг стальной',
    r'метал{1,2}опрокат\w*': 'металлопрокат',
    r'нержав\w+': 'нержавейка',
    r'оцинков\w+': 'оцинковка',

    # Бетон и цемент
    r'цемент\w*\s*[МмMm]?\s*\d*': 'цемент',
    r'бетон\w*\s*[МмBbВв]?\s*\d*': 'бетон',
    r'пескобетон\w*': 'пескобетон',
    r'раствор\w*\s*(кладочн|штукатурн)?\w*': 'раствор',
    r'ЖБИ|жби': 'ЖБИ',
    r'плит[аыу]\s*(перекрытия|дорожн|ПК|ПБ)\w*': 'плита',

    # Пиломатериалы
    r'доск[аиу]\w*\s*(обрезн|необрезн|строган)?\w*': 'доска',
    r'брус\w*\s*\d*[хx×]\d*': 'брус',
    r'фанер[аыу]\w*': 'фанера',
    r'OSB|ОСП|осб': 'OSB',
    r'пиломатериал\w*': 'пиломатериалы',
    r'вагонк[аиу]\w*': 'вагонка',

    # Кровля и изоляция
    r'утеплител[ья]\w*': 'утеплитель',
    r'(мин|минерал\w*)\s*ват[аыу]\w*': 'минвата',
    r'пенопласт\w*': 'пенопласт',
    r'пеноплекс\w*': 'пеноплекс',
    r'(мягк|рулонн)\w*\s*кровл\w*': 'кровля мягкая',
    r'черепиц[аыу]\w*': 'черепица',
    r'металлочерепиц[аыу]\w*': 'металлочерепица',

    # Сыпучие
    r'песо?к\w*\s*(карьерн|речн|строительн)?\w*': 'песок',
    r'щебен[ья]\w*|щебн\w*|щебёнк\w*': 'щебень',
    r'ПГС|пгс|песчано[\s-]гравийн\w*': 'ПГС',
    r'керамзит\w*': 'керамзит',
    r'грунт\w*': 'грунт',

    # Кирпич и блоки
    r'кирпич\w*\s*(керамич|силикат|облицов|рядов)?\w*': 'кирпич',
    r'газобетон\w*|газоблок\w*': 'газобетон',
    r'пенобетон\w*|пеноблок\w*': 'пеноблок',
    r'керамзитобетон\w*|керамзитоблок\w*': 'керамзитоблок',
    r'блок\w*\s*(стенов|фундаментн|бетонн)?\w*': 'блок',

    # Сухие смеси
    r'штукатурк[аиу]\w*': 'штукатурка',
    r'шпатлёвк[аиу]\w*|шпаклёвк[аиу]\w*': 'шпатлёвка',
    r'клей\w*\s*(плиточн|для\s+блоков)?\w*': 'клей',
    r'наливно[йе]\s*пол\w*': 'наливной пол',
    r'грунтовк[аиу]\w*': 'грунтовка',

    # Крепёж
    r'саморез\w*': 'саморезы',
    r'гвозд[ьией]\w*': 'гвозди',
    r'анкер\w*': 'анкеры',
}

# Агро — вторая ниша (на будущее, пока не парсить активно)
AGRICULTURE_PRODUCTS = {
    r'пшениц[аыу]\w*': 'пшеница',
    r'ячмен[ья]\w*': 'ячмень',
    r'кукуруз[аыу]\w*': 'кукуруза',
    r'подсолнечник\w*|семечк\w*': 'подсолнечник',
    r'соев?\w*\s*(бобы|шрот|масло)?': 'соя',
    r'сахар\w*\s*(песок)?': 'сахар',
    r'масло\s*(подсолнечн|растительн)\w*': 'масло подсолнечное',
    r'мук[аиу]\w*': 'мука',
}

# Объединённый словарь для текущего парсинга
PRODUCT_PATTERNS = {**CONSTRUCTION_PRODUCTS}

# Price patterns - more specific to avoid matching model numbers
PRICE_PATTERNS = [
    # Dot-as-thousand-separator: "130.000", "1.500.000" (Russian convention)
    # Must be first to match before explicit markers split "1.500.000" into "1.500"
    r'(\d{1,3}(?:\.\d{3})+)',
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
    # B2B: "48 500 руб/тонна", "3200 за м³", "4200/тн"
    r'(\d+(?:\s\d{3})*)\s*(?:руб|₽|р)?\s*[/за]\s*(?:тонн[аыу]?|тн|т\b|м[²³23]|куб|шт|рулон|лист|мешок|поддон|вагон)',
    # B2B: "от 45000", "от 45 000"
    r'от\s+(\d+(?:\s\d{3})*)\s*(?:руб|₽|р)?',
]

# Unit patterns for B2B price-per-unit extraction
UNIT_PATTERNS = [
    (r'(?:руб|₽|р)\s*/?\s*(тонн[аыу]?|тн|т\b)', 'тонна'),
    (r'(?:руб|₽|р)\s*/?\s*(м[²2]|кв\.?\s*м)', 'м²'),
    (r'(?:руб|₽|р)\s*/?\s*(м[³3]|куб\.?\s*м)', 'м³'),
    (r'(?:руб|₽|р)\s*/?\s*(шт|штук)', 'шт'),
    (r'(?:руб|₽|р)\s*/?\s*(рулон)', 'рулон'),
    (r'(?:руб|₽|р)\s*/?\s*(лист)', 'лист'),
    (r'(?:руб|₽|р)\s*/?\s*(мешок|мешк)', 'мешок'),
    (r'(?:руб|₽|р)\s*/?\s*(поддон)', 'поддон'),
    (r'(?:руб|₽|р)\s*/?\s*(вагон)', 'вагон'),
]

# Phone number patterns to detect warm deals
PHONE_PATTERNS = [
    r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 (999) 123-45-67
    r'\+?[78]\d{10}',  # +79991234567
    r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b',  # 999-123-45-67
]

# Region patterns - expanded list with common abbreviations
REGIONS = [
    'москва', 'москве', 'москву', 'москвы', 'мск', 'moscow', 'мос',
    'питер', 'питере', 'спб', 'санкт-петербург', 'санкт-петербурге', 'петербург', 'петербурге', 'ленинград',
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
    'воскресенск',
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
    'москве': 'Москва',
    'москву': 'Москва',
    'москвы': 'Москва',
    'moscow': 'Москва',
    'мос': 'Москва',
    'спб': 'Санкт-Петербург',
    'питер': 'Санкт-Петербург',
    'питере': 'Санкт-Петербург',
    'санкт-петербург': 'Санкт-Петербург',
    'санкт-петербурге': 'Санкт-Петербург',
    'петербург': 'Санкт-Петербург',
    'петербурге': 'Санкт-Петербург',
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
    'воскресенск': 'Воскресенск',
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


def extract_product(text: str) -> tuple[str | None, str | None]:
    """Извлекает продукт и нишу из текста.

    Returns:
        (product_name, niche) — например ('арматура А500С', 'стройматериалы')
    """
    text_lower = text.lower()

    # Сначала проверяем стройматериалы
    for pattern, product_name in CONSTRUCTION_PRODUCTS.items():
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            # Извлечь полное описание (включая марку/размер)
            full_product = match.group(0).strip()
            return (full_product or product_name, 'стройматериалы')

    # Потом агро (когда включим)
    # for pattern, product_name in AGRICULTURE_PRODUCTS.items():
    #     match = re.search(pattern, text_lower, re.IGNORECASE)
    #     if match:
    #         full_product = match.group(0).strip()
    #         return (full_product or product_name, 'сельхоз')

    # Fallback: извлекаем текст после ключевого слова купли/продажи
    all_keywords = BUY_KEYWORDS + SELL_KEYWORDS
    for keyword in all_keywords:
        if keyword in text_lower:
            idx = text_lower.find(keyword)
            after_keyword = text[idx + len(keyword):].strip()
            chunk = re.split(r'[,\n]|(?:\d+\s*(?:т\.?р|тыс|к|руб|р|₽))', after_keyword)[0].strip()
            if chunk and len(chunk) > 2:
                chunk = re.sub(r'^[!.\s]+', '', chunk)
                chunk = chunk[:100]
                if chunk:
                    return (chunk, None)

    return (None, None)


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
                price_str = match.group(1).replace(' ', '')
                # Detect dot-as-thousand-separator: "130.000" → "130000"
                if re.match(r'^\d{1,3}(\.\d{3})+$', price_str):
                    price_str = price_str.replace('.', '')
                else:
                    price_str = price_str.replace(',', '.')
                price = Decimal(price_str)

                # Проверяем множитель 'к' или 'тыс'
                full_match = match.group(0).lower()
                if any(m in full_match for m in ['к', 'тыс', 'т.р', 'тр']):
                    price *= 1000

                # Проверка диапазона — от 100 руб/шт (крепёж) до 50M (вагон)
                if 100 <= price <= 50_000_000:
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


def extract_price_unit(text: str) -> str | None:
    """Извлекает единицу измерения из выражения цены-за-единицу.

    Примеры:
        '4200/тн' → 'тонна'
        '47000р/тн' → 'тонна'
        '580р/м²' → 'м²'
        '12000 руб/м³' → 'м³'
    """
    PRICE_UNIT_PATTERNS = [
        (r'\d\s*/\s*(тонн[аыу]?|тн|т)\b', 'тонна'),
        (r'(?:руб|₽|р)\s*/?\s*(тонн[аыу]?|тн|т)\b', 'тонна'),
        (r'\d\s*/\s*(м[²2]|кв\.?\s*м)', 'м²'),
        (r'(?:руб|₽|р)\s*/?\s*(м[²2]|кв\.?\s*м)', 'м²'),
        (r'\d\s*/\s*(м[³3]|куб\.?\s*м)', 'м³'),
        (r'(?:руб|₽|р)\s*/?\s*(м[³3]|куб\.?\s*м)', 'м³'),
        (r'\d\s*/\s*(шт|штук)', 'шт'),
        (r'(?:руб|₽|р)\s*/?\s*(шт|штук)', 'шт'),
        (r'\d\s*/\s*(рулон)', 'рулон'),
        (r'\d\s*/\s*(лист)', 'лист'),
        (r'\d\s*/\s*(мешок|мешк)', 'мешок'),
        (r'\d\s*/\s*(поддон)', 'поддон'),
        (r'\d\s*/\s*(вагон)', 'вагон'),
    ]
    text_lower = text.lower()
    for pattern, unit in PRICE_UNIT_PATTERNS:
        if re.search(pattern, text_lower):
            return unit
    return None


def extract_volume(text: str) -> tuple[float | None, str | None]:
    """Извлекает объём и единицу из текста.

    Примеры:
        '20 тонн' → (20.0, 'тонна')
        '1 вагон' → (1.0, 'вагон')
        '500 м²' → (500.0, 'м²')
        '3 фуры' → (3.0, 'фура')
    """
    VOLUME_PATTERNS = [
        (r'(\d[\d\s.,]*\d?)\s*(тонн[аыу]?|тн|т\b)', 'тонна'),
        (r'(\d[\d\s.,]*\d?)\s*(вагон\w*)', 'вагон'),
        (r'(\d[\d\s.,]*\d?)\s*(фур[аыу]\w*|машин[аыу]\w*)', 'фура'),
        (r'(\d[\d\s.,]*\d?)\s*(м[²2]|кв\.?\s*м\w*)', 'м²'),
        (r'(\d[\d\s.,]*\d?)\s*(м[³3]|куб\w*)', 'м³'),
        (r'(\d[\d\s.,]*\d?)\s*(шт|штук\w*)', 'шт'),
        (r'(\d[\d\s.,]*\d?)\s*(рулон\w*)', 'рулон'),
        (r'(\d[\d\s.,]*\d?)\s*(лист\w*)', 'лист'),
        (r'(\d[\d\s.,]*\d?)\s*(поддон\w*|палет\w*)', 'поддон'),
        (r'(\d[\d\s.,]*\d?)\s*(мешк\w*|мешок)', 'мешок'),
        (r'(\d[\d\s.,]*\d?)\s*(пач[ек]\w*|пачка)', 'пачка'),
    ]
    for pattern, unit in VOLUME_PATTERNS:
        match = re.search(pattern, text.lower())
        if match:
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                return (float(num_str), unit)
            except ValueError:
                continue
    return (None, None)


# Синонимы продуктов для матчинга
_PRODUCT_SYNONYMS = {
    frozenset({'профнастил', 'профлист'}),
    frozenset({'доска', 'пиломатериал'}),
    frozenset({'газобетон', 'газоблок'}),
    frozenset({'пеноблок', 'пенобетон'}),
    frozenset({'щебень', 'щебёнка'}),
    frozenset({'минвата', 'утеплитель'}),
}


def _normalize_product(product: str) -> str:
    """Нормализация названия продукта для матчинга."""
    text = product.lower().strip()
    # Убрать марки: А500С, М500, В25, D500, F150
    text = re.sub(r'[АаAa]\d+[СсCcВвBb]?\d*', '', text)
    text = re.sub(r'[МмMm]\d+', '', text)
    text = re.sub(r'[ВвBb]\d+', '', text)
    text = re.sub(r'[DdДд]\d+', '', text)
    text = re.sub(r'[FfФф]\d+', '', text)
    # Убрать размеры: 12мм, 150x150, ∅10
    text = re.sub(r'\d+\s*[хx×]\s*\d+', '', text)
    text = re.sub(r'[∅⌀]?\d+\s*мм', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def _products_match(product_a: str, product_b: str) -> bool:
    """Матчинг продуктов для B2B-опта.

    Правила:
    1. Нормализация: lower + удалить марки (А500С, М500, В25)
    2. Точное совпадение нормализованного названия → True
    3. Корневое совпадение: 'арматура' ↔ 'арматуру' → True
    4. Категорийное: 'профнастил' ↔ 'профлист' → True (синонимы)
    5. Иначе: ≥50% пересечение значимых токенов (≥4 символов)
    """
    if not product_a or not product_b:
        return False

    a = _normalize_product(product_a)
    b = _normalize_product(product_b)

    if a == b:
        return True

    # Проверить синонимы
    for syn_group in _PRODUCT_SYNONYMS:
        if a in syn_group and b in syn_group:
            return True

    # Проверить корневое совпадение (первые 4 символа)
    if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]:
        return True

    # Токенизация
    tokens_a = {t for t in a.split() if len(t) >= 4}
    tokens_b = {t for t in b.split() if len(t) >= 4}
    if not tokens_a or not tokens_b:
        return False

    intersection = tokens_a & tokens_b
    min_len = min(len(tokens_a), len(tokens_b))
    return len(intersection) / min_len >= 0.5


async def try_match_orders(db, new_order: Order) -> Optional[DetectedDeal]:
    """
    Try to match a new order with existing opposite orders.
    Buy order matches with Sell orders and vice versa.
    """
    opposite_type = OrderType.SELL if new_order.order_type == OrderType.BUY else OrderType.BUY

    product_name = new_order.product or ""

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
        candidate_product = candidate.product or ""

        if _products_match(product_name, candidate_product):
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
            await db.flush()

            # Explicitly set relationships so they're available without refresh
            deal.sell_order = sell_order
            deal.buy_order = buy_order

            # Mark orders as matched (deactivate)
            buy_order.is_active = False
            sell_order.is_active = False

            logger.info(f"Created deal #{deal.id}: {deal.product} (margin: {margin})")
            return deal

    return None


def _passive_save_message(db, negotiation, message_text: str, role: MessageRole, target: MessageTarget):
    """Save incoming message passively (no AI response). Manager sees it in chat."""
    msg = NegotiationMessage(
        negotiation_id=negotiation.id,
        role=role,
        target=target,
        content=message_text,
    )
    db.add(msg)
    logger.info(
        f">>> Passive save: сообщение сохранено для переговоров #{negotiation.id} "
        f"(stage={negotiation.stage.value}, AI НЕ отвечает)"
    )


# Stages where AI ALWAYS stays silent (deal done or manager took over)
_AI_ALWAYS_SILENT = {NegotiationStage.CLOSED, NegotiationStage.HANDED_TO_MANAGER}


def _should_ai_respond(negotiation, side: str, ai_mode: str = "autopilot") -> bool:
    """
    Check if AI should respond for this side of the negotiation.

    Each side (seller/buyer) is independent:
    - copilot mode → always silent (manager handles all communication)
    - CLOSED / HANDED_TO_MANAGER → always silent
    - WARM → silent only for the side that already gave phone
    - Otherwise → AI responds
    """
    # In copilot mode, AI never auto-responds — manager handles communication
    if ai_mode == "copilot":
        return False

    if negotiation.stage in _AI_ALWAYS_SILENT:
        return False

    if negotiation.stage == NegotiationStage.WARM:
        deal = negotiation.deal
        if side == "seller" and deal.seller_phone:
            # Seller already gave phone — no need to talk further
            return False
        if side == "buyer" and deal.buyer_phone:
            # Buyer already gave phone — no need to talk further
            return False
        # The OTHER side went warm, but this side still needs to give phone
        return True

    return True


async def check_negotiation_response(
    db, sender_id: int, message_text: str, reply_to_msg_id: Optional[int] = None
) -> bool:
    """
    Проверка, является ли сообщение ответом на активные переговоры.
    Если да - обрабатывает через AI negotiator.

    Each side (seller/buyer) is handled independently:
    - If this side already gave phone → passive save
    - If the OTHER side gave phone but this side hasn't → AI continues
    - CLOSED / HANDED_TO_MANAGER → always passive

    Args:
        db: Database session
        sender_id: Telegram sender ID
        message_text: Message text
        reply_to_msg_id: Telegram message ID that this message replies to

    Returns:
        True if message was a negotiation response
    """
    if not sender_id:
        logger.info(f"check_negotiation_response: sender_id пустой, пропускаем")
        return False

    try:
        logger.info(f">>> check_negotiation_response: sender_id={sender_id}, текст: '{message_text[:50]}...'")

        # Определяем режим AI для управления авто-ответами
        from src.services.ai_copilot import get_ai_mode
        ai_mode = await get_ai_mode(db)

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
            if not _should_ai_respond(negotiation, "seller", ai_mode=ai_mode):
                _passive_save_message(db, negotiation, message_text, MessageRole.SELLER, MessageTarget.SELLER)
                await db.flush()
                return True
            success = await process_seller_response(negotiation, message_text, db, reply_to_msg_id=reply_to_msg_id)
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
            if not _should_ai_respond(negotiation, "buyer", ai_mode=ai_mode):
                _passive_save_message(db, negotiation, message_text, MessageRole.BUYER, MessageTarget.BUYER)
                await db.flush()
                return True
            success = await process_buyer_response(negotiation, message_text, db, reply_to_msg_id=reply_to_msg_id)
            logger.info(f">>> process_buyer_response вернул: {success}")
            return True

        logger.info(f">>> Активные переговоры для sender_id={sender_id} не найдены")
        return False

    except Exception as e:
        # Если ошибка с enum или БД - логируем ERROR и возвращаем False
        logger.error(f"!!! ОШИБКА при проверке переговоров для sender_id={sender_id}: {e}", exc_info=True)
        return False


async def _resolve_event_text(event, telegram_service) -> Optional[str]:
    """
    Convert any Telethon event to text, handling voice/media.

    Returns:
        Resolved text string or None if message should be skipped.
    """
    message = event.message
    raw_text = event.text  # None for pure media messages

    # Voice message handling (voice notes or audio documents)
    if message.voice or (
        message.document
        and getattr(message.document, 'mime_type', None)
        and message.document.mime_type.startswith('audio/')
    ):
        try:
            audio_bytes = await telegram_service.client.download_media(message, bytes)
            if audio_bytes:
                from src.services.transcriber import transcribe_voice
                mime = getattr(message.document, 'mime_type', 'audio/ogg') if message.document else 'audio/ogg'
                ext = mime.split('/')[-1] if '/' in mime else 'ogg'
                transcribed = await transcribe_voice(audio_bytes, f"voice.{ext}")
                if transcribed:
                    return f"[голосовое]: {transcribed}"
                else:
                    return "[голосовое сообщение]"
            else:
                return "[голосовое сообщение]"
        except Exception as e:
            logger.error(f"Voice download/transcribe error: {e}")
            return "[голосовое сообщение]"

    # Text messages (including captions on media)
    if raw_text:
        return raw_text

    # Pure media without caption
    if message.photo:
        return "[фото]"
    if message.video:
        return "[видео]"
    if getattr(message, 'document', None):
        return "[документ]"
    if getattr(message, 'sticker', None):
        return "[стикер]"

    # Truly empty (service messages, polls, etc.)
    return None


_message_buffer = None


def _get_message_buffer():
    """Get or create the global message buffer."""
    global _message_buffer
    if _message_buffer is None:
        from src.services.message_buffer import MessageBuffer
        _message_buffer = MessageBuffer(
            resolve_fn=_resolve_event_text,
            handler_fn=_process_message_internal,
        )
    return _message_buffer


async def handle_new_message(event, telegram_service) -> None:
    """
    Handle incoming Telegram message.
    Buffers consecutive messages from the same sender before processing.

    Args:
        event: Telethon NewMessage event
        telegram_service: TelegramService instance
    """
    # Skip own messages early (before buffering)
    if telegram_service.is_own_message(event.sender_id):
        return

    buf = _get_message_buffer()
    await buf.on_message(event, telegram_service)


async def _process_message_internal(event, telegram_service, raw_text: str = None) -> None:
    """
    Internal message processing. Called by the buffer with resolved/merged text.

    Args:
        event: Telethon NewMessage event (first event if merged)
        telegram_service: TelegramService instance
        raw_text: Pre-resolved text (from buffer). If None, resolves from event.
    """
    try:
        # Resolve text if not provided (direct call without buffer)
        if raw_text is None:
            raw_text = await _resolve_event_text(event, telegram_service)
        if not raw_text or raw_text.strip() == "":
            return

        message = event.message
        chat = await event.get_chat()
        sender = await event.get_sender()

        chat_id = event.chat_id
        message_id = message.id
        # In channels, sender_id can be None - use chat_id as fallback
        sender_id = event.sender_id or chat_id
        chat_title = getattr(chat, 'title', None) or getattr(chat, 'first_name', '') or str(chat_id)

        # Extract reply_to_msg_id for reply context tracking
        reply_to_msg_id = None
        if hasattr(message, 'reply_to') and message.reply_to:
            reply_to_msg_id = getattr(message.reply_to, 'reply_to_msg_id', None)

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
                is_negotiation_response = await check_negotiation_response(db, sender_id, raw_text, reply_to_msg_id=reply_to_msg_id)
                logger.info(f">>> check_negotiation_response вернул: {is_negotiation_response}")
            except Exception as neg_check_error:
                logger.error(f"!!! Ошибка в check_negotiation_response: {neg_check_error}", exc_info=True)
                # Продолжаем обработку как обычное сообщение

            if not is_negotiation_response:
                # Если это не ответ на переговоры - проверяем, является ли это новой заявкой
                order_type = detect_order_type(raw_text)

                if order_type:
                    # Извлекаем товар, цену, регион, объём
                    product, niche = extract_product(raw_text)
                    price = extract_price(raw_text)
                    region = extract_region(raw_text)
                    volume, unit = extract_volume(raw_text)
                    quantity_str = extract_quantity(raw_text)

                    # Если unit не найден через volume — пробуем из цены-за-единицу
                    if not unit:
                        unit = extract_price_unit(raw_text)

                    # Если продукт не найден — используем fallback
                    if not product:
                        product = "Товар"

                    logger.info(
                        f"Parsed: type={order_type.value}, product={product}, "
                        f"niche={niche}, price={price}, region={region}, "
                        f"volume={volume}, unit={unit}"
                    )

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
                            quantity=quantity_str,
                            region=region,
                            raw_text=raw_text,
                            contact_info=contact_info,
                            is_active=True,
                            platform='telegram',
                            niche=niche,
                            unit=unit,
                            volume_numeric=Decimal(str(volume)) if volume else None,
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
