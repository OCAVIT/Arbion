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

from src.services import llm
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

# Ответы на положительную реакцию (первый ответ) — универсальные
FOLLOWUP_POSITIVE_FIRST = [
    "отлично! а состояние какое? есть нюансы?",
    "супер, что по состоянию скажешь?",
    "хорошо, а всё в порядке? нюансы какие-нибудь есть?",
    "понял, расскажи про состояние - важно чтобы всё было ок",
    "ок, а по качеству как? есть что-нибудь?",
]

# Уточнение цены (для продавца)
FOLLOWUP_PRICE = [
    "понял, а по цене можно подвинуться немного?",
    "ясно, если скинешь чуть-чуть - сразу заберу",
    "а торг будет? могу подъехать сегодня",
    "а если чуть дешевле - возьму сейчас",
    "по цене договоримся? заберу быстро",
]

# Уточнение бюджета покупателя (никогда не называем цену!)
FOLLOWUP_BUYER_PRICE = [
    "а на какой бюджет рассчитываешь?",
    "по сумме что-нибудь подойдёт? какой бюджет?",
    "а на какую сумму смотришь?",
    "а по бюджету как? сколько готов отдать?",
]

# Уточнение состояния (второй этап) — универсальные
FOLLOWUP_CONDITION = [
    "понял, а состояние какое? всё в порядке?",
    "ясно, а по качеству как? нюансы есть?",
    "хорошо, а всё работает? дефектов нет?",
    "ок, а ещё какие-нибудь нюансы есть?",
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

# Уточнение города и характеристик (exchanges 2-3) — универсальные
FOLLOWUP_CITY_OR_SPECS = [
    "а ты в каком городе?",
    "а где территориально находишься?",
    "а какие основные характеристики?",
    "а в каком городе можно забрать?",
    "а по параметрам - что можешь сказать?",
    "а откуда? в каком городе?",
]

# Первый ответ покупателю (уточнение предпочтений, НЕ состояние!)
FOLLOWUP_BUYER_FIRST = [
    "понял, а какой именно вариант интересует?",
    "хорошо, а какие предпочтения? что важно?",
    "ясно, а что-то конкретное ищешь или в целом?",
    "понял, а по каким параметрам выбираешь?",
]

# Уточнение характеристик (для продавца)
FOLLOWUP_SPECS = [
    "а какие основные характеристики?",
    "а по параметрам что можешь сказать?",
    "а подробнее по характеристикам расскажешь?",
]

# Уточнение если непонятно
FOLLOWUP_UNCLEAR = [
    "не совсем понял, так продаёшь ещё?",
    "можно подробнее? интересует покупка",
    "так актуально или нет?",
    "прости, не понял - в продаже ещё?",
]

# Шаблоны для уточнения недостающих данных (fallback)
MISSING_DATA_TEMPLATES = {
    "price_seller": [
        "а сколько просишь?",
        "а по цене что скажешь?",
        "а за сколько отдашь?",
    ],
    "price_buyer": [
        "а на какой бюджет рассчитываешь?",
        "по сумме как? какой бюджет?",
        "а на какую сумму смотришь?",
    ],
    "region": [
        "а ты откуда? в каком городе?",
        "а в каком городе?",
        "а где территориально?",
    ],
    "quantity": [
        "а сколько штук нужно?",
        "по количеству - сколько?",
    ],
}

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
    'комплект', 'дефект', 'качество', 'износ', 'нюансы', 'целый',
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


def _is_condition_question(last_ai_message: str) -> bool:
    """Проверяет, спрашивал ли бот о состоянии/дефектах."""
    lower = last_ai_message.lower()
    condition_question_markers = [
        'трещин', 'царапин', 'сколы', 'сколов',
        'косяки', 'косяков', 'дефект', 'состояние', 'работает',
        'качество', 'нюансы', 'в порядке', 'износ',
    ]
    return any(marker in lower for marker in condition_question_markers)


# Слова-отрицания в коротких ответах: "нет"/"нету"/"неа"/"неа-нету" = нет проблем (в контексте вопроса о дефектах)
_DENIAL_WORD = r'(?:нет[уа]?|не[ату]+|неа)'
_SHORT_DENIAL_PATTERN = re.compile(
    rf'^[\s]*{_DENIAL_WORD}(?:[\s,.\-!]+{_DENIAL_WORD})?[\s,.\-!]*$', re.IGNORECASE
)

# Слова-проблемы, которые "нет" может отрицать: "дефектов нет" = позитив, не негатив
_NEGATED_PROBLEM_STEMS = [
    'дефект', 'царапин', 'скол', 'трещин', 'проблем',
    'повреждени', 'косяк', 'нюанс', 'претензи', 'поломк', 'поломок',
]


def _is_negated_problem(text_lower: str) -> bool:
    """Check if 'нет' negates a problem word (e.g., 'дефектов нет' = positive, not rejection)."""
    for stem in _NEGATED_PROBLEM_STEMS:
        # "дефектов нет", "царапин нет"
        if re.search(rf'{stem}\w*\s+нет\b', text_lower):
            return True
        # "нет дефектов", "нет проблем"
        if re.search(rf'\bнет\s+{stem}', text_lower):
            return True
    return False


def _analyze_discussed_topics(context: List[dict]) -> set:
    """Scan conversation context for already discussed topics."""
    discussed = set()
    all_text = " ".join(m["content"].lower() for m in context)

    condition_markers = [
        'состояние', 'царапин', 'сколы', 'дефект', 'работает', 'идеал', 'комплект', 'коробка',
        'износ', 'повреждени', 'исправн', 'качество', 'целост',
    ]
    city_markers = [
        'город', 'откуда', 'территориально', 'москв', 'мск', 'спб', 'питер', 'екб',
        'расположен', 'регион', 'находи',
    ]
    specs_markers = [
        'память', 'конфигурац', 'цвет', 'гб', 'gb', 'процессор', 'версия',
        'параметр', 'размер', 'марка', 'модель', 'тип', 'сорт',
    ]
    preferences_markers = [
        'предпочтен', 'интересует', 'какой именно', 'что ищешь', 'что нужно',
    ]

    if any(m in all_text for m in condition_markers):
        discussed.add("condition")
    if any(m in all_text for m in city_markers):
        discussed.add("city")
    if any(m in all_text for m in specs_markers):
        discussed.add("specs")
    if any(m in all_text for m in preferences_markers):
        discussed.add("preferences")

    return discussed


def build_conversation_summary(context: List[dict]) -> str:
    """
    Build a short structured summary of the conversation for the LLM's memory section.

    Each exchange is compressed to one line. Unanswered questions from the counterparty
    are flagged with (НЕ ОТВЕЧЕНО).

    Returns:
        Multi-line summary string, or empty string if context has < 2 messages.
    """
    if len(context) < 2:
        return ""

    lines = []
    step = 0
    i = 0
    _question_markers = ["?", "ты бот", "кто ты", "почему", "зачем", "откуда", "сколько"]

    while i < len(context):
        msg = context[i]
        role_label = "Ты" if msg["role"] == "ai" else "Собеседник"
        content_short = msg["content"][:80].replace("\n", " ")

        # Try to pair with next message if roles differ
        if i + 1 < len(context) and context[i]["role"] != context[i + 1]["role"]:
            next_msg = context[i + 1]
            next_role = "Ты" if next_msg["role"] == "ai" else "Собеседник"
            next_content = next_msg["content"][:80].replace("\n", " ")
            step += 1
            # Check if the counterparty's response contains an unanswered question
            counterparty_msg = next_msg if next_msg["role"] != "ai" else msg
            has_question = any(m in counterparty_msg["content"].lower() for m in _question_markers)
            # Flag if counterparty asked a question AND it's the last pair (no AI response after)
            if has_question and counterparty_msg["role"] != "ai" and i + 2 >= len(context):
                lines.append(
                    f"{step}. {role_label}: {content_short} → {next_role}: {next_content} "
                    f"→ (НЕ ОТВЕЧЕНО — ответь!)"
                )
            else:
                lines.append(f"{step}. {role_label}: {content_short} → {next_role}: {next_content}")
            i += 2
            continue

        # Unpaired message
        step += 1
        is_question = any(m in msg["content"].lower() for m in _question_markers)
        if msg["role"] != "ai" and is_question:
            lines.append(f"{step}. Собеседник спросил: {content_short} → (НЕ ОТВЕЧЕНО — ответь!)")
        else:
            lines.append(f"{step}. {role_label}: {content_short}")
        i += 1

    return "\n".join(lines)


def _detect_unanswered_question(context: List[dict]) -> Optional[str]:
    """
    Check if the last non-AI message contains a question that hasn't been answered.

    Returns the question text if found, None otherwise.
    """
    if not context:
        return None

    last_msg = context[-1]
    if last_msg["role"] == "ai":
        return None

    text = last_msg["content"]
    question_markers = ["?", "ты бот", "кто ты", "почему", "зачем", "откуда"]
    if any(marker in text.lower() for marker in question_markers):
        return text

    return None


def detect_missing_fields(deal, target: str, context: Optional[List[dict]] = None) -> dict:
    """
    Определяет, каких данных не хватает в сделке/заявке.

    Args:
        deal: DetectedDeal
        target: 'seller' или 'buyer'
        context: conversation context for topic analysis

    Returns:
        {'missing': ['price', 'region', ...], 'prompt_hint': str}
    """
    missing = []
    hints = []

    discussed = _analyze_discussed_topics(context) if context else set()

    if target == "seller":
        order = getattr(deal, 'sell_order', None)
        # Check condition
        if not getattr(deal, 'seller_condition', None) and "condition" not in discussed:
            missing.append("condition")
            hints.append("состояние не известно — узнай про состояние товара")
        # Check city
        if not getattr(deal, 'seller_city', None) and not deal.region and "city" not in discussed:
            missing.append("city")
            hints.append("город не указан — узнай откуда продавец")
        # Check specs
        if not getattr(deal, 'seller_specs', None) and "specs" not in discussed:
            missing.append("specs")
            hints.append("характеристики не известны — узнай конфигурацию (память, цвет)")
        # Check price
        if not deal.sell_price and (not order or not order.price):
            missing.append("price")
            hints.append("цена не указана — узнай сколько просит за товар")
    else:
        order = getattr(deal, 'buy_order', None)
        # Check preferences
        if not getattr(deal, 'buyer_preferences', None) and "specs" not in discussed and "preferences" not in discussed:
            missing.append("preferences")
            hints.append("предпочтения не известны — узнай что именно интересует")
        # Check city
        if not deal.region and "city" not in discussed:
            missing.append("city")
            hints.append("город не указан — узнай откуда покупатель")
        # Check price/budget
        if not deal.buy_price and (not order or not order.price):
            missing.append("price")
            hints.append("бюджет не указан — узнай на какую сумму рассчитывает")

    # If we still have missing fields, tell LLM NOT to ask for phone yet
    phone_block = ""
    if missing:
        missing_labels = []
        if "condition" in missing:
            missing_labels.append("состояние")
        if "city" in missing:
            missing_labels.append("город")
        if "specs" in missing:
            missing_labels.append("характеристики")
        if "preferences" in missing:
            missing_labels.append("предпочтения")
        if "price" in missing:
            missing_labels.append("цену" if target == "seller" else "бюджет")
        if missing_labels:
            phone_block = f"\nОБЯЗАТЕЛЬНО — НЕ ПРОСИ ТЕЛЕФОН пока не узнал: {', '.join(missing_labels)}."

    prompt_hint = ""
    if hints:
        prompt_hint = "ВАЖНО — следующие данные отсутствуют, естественно вплети вопросы в разговор:\n"
        prompt_hint += "\n".join(f"- {h}" for h in hints)
        prompt_hint += "\nСпрашивай по одному, не все сразу."
        prompt_hint += phone_block

    return {"missing": missing, "prompt_hint": prompt_hint}


def analyze_response(text: str, last_ai_message: str = "") -> Tuple[str, Optional[str]]:
    """
    Анализ ответа продавца/покупателя.

    Args:
        text: Текст ответа
        last_ai_message: Последнее сообщение бота (для контекста)

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

    # Контекстная проверка: если бот спрашивал о дефектах,
    # а ответ — "нет"/"нету" или "дефектов нет"/"нет проблем", это значит "нет проблем" = позитив
    if last_ai_message and _is_condition_question(last_ai_message):
        if _SHORT_DENIAL_PATTERN.match(text_lower) or _is_negated_problem(text_lower):
            return 'positive', None

    # Проверка на явный негатив (продано, не продаю, и т.д.)
    # "нет" проверяем только как полное слово, не как подстроку
    for keyword in NEGATIVE_KEYWORDS:
        if keyword == 'нет':
            # "нет" только как отдельное слово (не "нету", "нетак" и т.д.)
            if re.search(r'\bнет\b', text_lower) and not re.search(r'\bнету\b', text_lower):
                # "дефектов нет" / "нет проблем" — это не отказ, а позитив
                if _is_negated_problem(text_lower):
                    continue
                return 'negative', None
        elif keyword in text_lower:
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


def _pick_missing_field_response(missing: List[str], target: str) -> Tuple[str, Optional[str]]:
    """Pick a template response for the first missing field."""
    field = missing[0]

    if target == "seller":
        if field == "condition":
            return 'respond', random.choice(FOLLOWUP_CONDITION)
        elif field == "city":
            return 'respond', random.choice(MISSING_DATA_TEMPLATES["region"])
        elif field == "specs":
            return 'respond', random.choice(FOLLOWUP_SPECS)
        elif field == "price":
            return 'respond', random.choice(FOLLOWUP_PRICE)
    else:  # buyer
        if field == "preferences":
            return 'respond', random.choice(FOLLOWUP_BUYER_FIRST)
        elif field == "city":
            return 'respond', random.choice(MISSING_DATA_TEMPLATES["region"])
        elif field == "price":
            return 'respond', random.choice(FOLLOWUP_BUYER_PRICE)

    return 'respond', random.choice(FOLLOWUP_UNCLEAR)


def determine_next_action(
    sentiment: str,
    phone: Optional[str],
    context: List[dict],
    stage: NegotiationStage,
    target: str = "seller",
    missing_fields: Optional[List[str]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Определение следующего действия на основе анализа.

    When missing_fields is provided, uses context-aware logic to ask only
    about data that's actually missing — prevents duplicate questions.

    Args:
        target: 'seller' или 'buyer' — с кем ведём диалог
        missing_fields: list of still-missing field names (from detect_missing_fields)

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

    # Контакт упомянут без номера - просим номер
    if sentiment == 'contact':
        return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)

    # --- Context-aware path (when missing_fields is provided) ---
    if missing_fields is not None:
        if missing_fields:
            return _pick_missing_field_response(missing_fields, target)
        # All fields collected → ask for phone
        return 'respond', random.choice(FOLLOWUP_ASK_CONTACT)

    # --- Legacy path (no missing_fields — backward compat) ---
    price_templates = FOLLOWUP_BUYER_PRICE if target == "buyer" else FOLLOWUP_PRICE

    if exchanges == 0:
        if sentiment in ['positive', 'price', 'condition']:
            if target == "buyer":
                if sentiment == 'price':
                    return 'respond', random.choice(price_templates)
                return 'respond', random.choice(FOLLOWUP_BUYER_FIRST)
            return 'respond', random.choice(FOLLOWUP_POSITIVE_FIRST)
        else:
            return 'respond', random.choice(FOLLOWUP_UNCLEAR)

    elif exchanges == 1:
        if sentiment == 'price':
            return 'respond', random.choice(price_templates)
        elif sentiment in ['positive', 'condition']:
            if target == "buyer":
                return 'respond', random.choice(FOLLOWUP_BUYER_FIRST)
            return 'respond', random.choice(FOLLOWUP_CONDITION)
        else:
            return 'respond', random.choice(FOLLOWUP_UNCLEAR)

    elif exchanges in [2, 3]:
        if target == "buyer":
            return 'respond', random.choice(FOLLOWUP_BUYER_PRICE)
        return 'respond', random.choice(FOLLOWUP_CITY_OR_SPECS)

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
# КРОСС-КОНТЕКСТ
# =====================================================

async def build_cross_context(deal: DetectedDeal, current_target: str, db: AsyncSession) -> Optional[str]:
    """
    Build cross-context info from the other side of the deal.

    For buyer: condition, city, specs from seller (NEVER price!)
    For seller: buyer budget, region
    """
    parts = []

    if current_target == "buyer":
        # Give buyer product info from seller (NEVER price!) — buyer can share this
        if deal.seller_condition:
            parts.append(f"Состояние: {deal.seller_condition}")
        if deal.seller_city:
            parts.append(f"Город: {deal.seller_city}")
        if deal.seller_specs:
            parts.append(f"Характеристики: {deal.seller_specs}")
    elif current_target == "seller":
        # Give seller info about buyer preferences (internal, don't reveal directly)
        if deal.buy_price:
            parts.append(f"Бюджет покупателя: {deal.buy_price}")
        if deal.region:
            parts.append(f"Регион покупателя: {deal.region}")

    if not parts:
        return None

    if current_target == "buyer":
        return "ИНФОРМАЦИЯ О ТОВАРЕ (используй для ответов покупателю, подавай как свои знания):\n" + "\n".join(f"- {p}" for p in parts)
    else:
        return "Внутренняя информация (используй для контекста, НЕ раскрывай напрямую):\n" + "\n".join(f"- {p}" for p in parts)


def _extract_condition_from_text(text: str) -> Optional[str]:
    """Try to extract condition info from seller response."""
    text_lower = text.lower()
    condition_markers = [
        'идеальн', 'отличн', 'хорош', 'норм', 'без царапин', 'без сколов',
        'как новый', 'без дефектов', 'без косяков', 'состояние',
        'царапин', 'потёртост', 'потертост', 'скол', 'трещин',
        'качество', 'износ', 'повреждени', 'целый',
        'работает', 'дефект', 'исправн', 'рабочи', 'сломан', 'битый',
    ]
    if any(m in text_lower for m in condition_markers):
        return text[:200].strip()
    return None


def _extract_specs_from_text(text: str) -> Optional[str]:
    """Try to extract specs (memory, color, config) from text."""
    text_lower = text.lower()
    specs_markers = [
        'гб', 'gb', 'тб', 'tb', 'память', 'озу', 'ram',
        'чёрный', 'черный', 'белый', 'серый', 'синий', 'красный', 'золотой',
        'pro max', 'pro', 'plus', 'ultra',
        'размер', 'марка', 'модель', 'тип', 'материал', 'мощность',
    ]
    if any(m in text_lower for m in specs_markers):
        return text[:200].strip()
    return None


def _extract_preferences_from_text(text: str) -> Optional[str]:
    """Try to extract buyer preferences from text."""
    text_lower = text.lower()
    pref_markers = [
        'цвет', 'размер', 'модель', 'тип', 'сорт', 'гб', 'gb',
        'память', 'конфигурац', 'комплект', 'версия', 'марка',
        'чёрный', 'черный', 'белый', 'серый', 'синий', 'красный', 'золотой',
        'pro', 'plus', 'max', 'ultra', 'mini',
        'материал', 'мощность',
    ]
    if any(m in text_lower for m in pref_markers):
        return text[:200].strip()
    return None


def collect_known_data(deal, target: str, context: Optional[List[dict]] = None) -> dict:
    """
    Collect already-known data about the deal for dynamic prompts.

    Args:
        deal: DetectedDeal
        target: 'seller' or 'buyer'
        context: conversation history for scanning

    Returns:
        dict with known fields: region, condition, specs, price, preferences, budget
    """
    known = {}

    if target == "seller":
        if getattr(deal, 'seller_city', None):
            known["region"] = deal.seller_city
        elif deal.region:
            known["region"] = deal.region
        if getattr(deal, 'seller_condition', None):
            known["condition"] = deal.seller_condition[:100]
        if getattr(deal, 'seller_specs', None):
            known["specs"] = deal.seller_specs[:100]
        if deal.sell_price:
            known["price"] = str(deal.sell_price)
    else:
        if deal.region:
            known["region"] = deal.region
        if getattr(deal, 'buyer_preferences', None):
            known["preferences"] = deal.buyer_preferences[:100]
        if deal.buy_price:
            known["budget"] = str(deal.buy_price)

    # Scan context for discussed topics that may contain data
    if context:
        discussed = _analyze_discussed_topics(context)
        # If city was discussed but not stored, mark it as known to avoid re-asking
        if "city" in discussed and "region" not in known:
            # Try to extract from context
            for msg in context:
                if msg["role"] != "ai":
                    from src.services.message_handler import extract_region
                    region = extract_region(msg["content"])
                    if region:
                        known["region"] = region
                        break

    return known


def build_ai_insight(deal) -> str:
    """Build a structured AI Insight summary from deal data."""
    parts = []

    # Seller summary
    seller_parts = []
    if deal.seller_city:
        seller_parts.append(deal.seller_city)
    if deal.seller_condition:
        seller_parts.append(f"состояние: {deal.seller_condition[:80]}")
    if deal.seller_specs:
        seller_parts.append(deal.seller_specs[:80])
    if deal.sell_price:
        seller_parts.append(f"цена: {deal.sell_price}")
    if deal.seller_phone:
        seller_parts.append(f"тел: {deal.seller_phone}")
    if seller_parts:
        parts.append(f"Продавец: {'; '.join(seller_parts)}")

    # Buyer summary
    buyer_parts = []
    if deal.region and not deal.seller_city:
        buyer_parts.append(deal.region)
    if deal.buyer_preferences:
        buyer_parts.append(deal.buyer_preferences[:80])
    if deal.buy_price:
        buyer_parts.append(f"бюджет: {deal.buy_price}")
    if deal.buyer_phone:
        buyer_parts.append(f"тел: {deal.buyer_phone}")
    if buyer_parts:
        parts.append(f"Покупатель: {'; '.join(buyer_parts)}")

    # Recommendation
    if deal.seller_phone and deal.buyer_phone:
        parts.append("Оба контакта получены — можно связывать стороны")
    elif deal.seller_phone:
        parts.append("Контакт продавца получен, ждём контакт покупателя")
    elif deal.buyer_phone:
        parts.append("Контакт покупателя получен, ждём контакт продавца")

    if not parts:
        return f"Переговоры в процессе по {deal.product}"

    return "\n".join(parts)


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

        # Определяем недостающие данные
        seller_missing = detect_missing_fields(deal, "seller")

        # Get listing text for context
        seller_listing_text = sell_order.raw_text if sell_order else None

        # Генерируем первое сообщение продавцу (LLM → fallback на шаблон)
        price_str = str(deal.sell_price) if deal.sell_price else None
        seller_message = await llm.generate_initial_message(
            "seller", deal.product, price_str,
            missing_data_hint=seller_missing["prompt_hint"],
            listing_text=seller_listing_text,
        )
        if not seller_message:
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
            buyer_missing = detect_missing_fields(deal, "buyer")
            # Get buy order listing text
            buy_order_result = await db.execute(select(Order).where(Order.id == deal.buy_order_id))
            buy_order = buy_order_result.scalar_one_or_none()
            buyer_listing_text = buy_order.raw_text if buy_order else None
            # НЕ передаём цену продавца покупателю — это убивает маржу
            buyer_message = await llm.generate_initial_message(
                "buyer", deal.product, None,
                missing_data_hint=buyer_missing["prompt_hint"],
                listing_text=buyer_listing_text,
            )
            if not buyer_message:
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
        deal = negotiation.deal

        # Извлекаем данные из ответа продавца (lazy import для избежания circular import)
        from src.services.message_handler import extract_price, extract_region, extract_quantity

        result_order = await db.execute(select(Order).where(Order.id == deal.sell_order_id))
        sell_order = result_order.scalar_one_or_none()

        if not deal.sell_price:
            extracted_price = extract_price(response_text)
            if extracted_price:
                deal.sell_price = extracted_price
                if sell_order:
                    sell_order.price = extracted_price
                if deal.buy_price:
                    deal.margin = deal.buy_price - extracted_price
                logger.info(f"Извлечена цена продавца {extracted_price} из ответа")

        if not deal.region:
            extracted_region = extract_region(response_text)
            if extracted_region:
                deal.region = extracted_region
                if sell_order:
                    sell_order.region = extracted_region
                logger.info(f"Извлечён регион '{extracted_region}' из ответа продавца")

        if sell_order and not sell_order.quantity:
            extracted_qty = extract_quantity(response_text)
            if extracted_qty:
                sell_order.quantity = extracted_qty
                logger.info(f"Извлечено количество '{extracted_qty}' из ответа продавца")

        # Extract condition, city, specs from seller response
        if not deal.seller_condition:
            extracted_condition = _extract_condition_from_text(response_text)
            if extracted_condition:
                deal.seller_condition = extracted_condition
                logger.info(f"Извлечено состояние: '{extracted_condition[:50]}...'")

        if not deal.seller_city:
            extracted_city = extract_region(response_text)
            if extracted_city:
                deal.seller_city = extracted_city
                if not deal.region:
                    deal.region = extracted_city
                    if sell_order:
                        sell_order.region = extracted_city
                logger.info(f"Извлечён город продавца: '{extracted_city}'")

        if not deal.seller_specs:
            extracted_specs = _extract_specs_from_text(response_text)
            if extracted_specs:
                deal.seller_specs = extracted_specs
                logger.info(f"Извлечены спеки: '{extracted_specs[:50]}...'")

        # Collect known data and determine missing fields
        known_data = collect_known_data(deal, "seller", context=context)
        seller_missing = detect_missing_fields(deal, "seller", context=context)

        # Get listing text and cross-context
        listing_text = sell_order.raw_text if sell_order else None
        cross_ctx = await build_cross_context(deal, "seller", db)

        # Build conversation summary for LLM memory
        conversation_summary = build_conversation_summary(context)

        # Пробуем LLM, fallback на шаблоны
        llm_result = await llm.generate_negotiation_response(
            role="seller",
            context=context,
            product=deal.product,
            price=str(deal.sell_price) if deal.sell_price else None,
            missing_data_hint=seller_missing["prompt_hint"],
            listing_text=listing_text,
            cross_context=cross_ctx,
            known_data=known_data,
            missing_fields=seller_missing["missing"],
            conversation_summary=conversation_summary,
        )

        if not llm_result:
            # Tier-2: try simpler LLM call before falling back to templates
            unanswered = _detect_unanswered_question(context)
            llm_result = await llm.generate_simple_response(context, unanswered)

        if llm_result:
            action = llm_result["action"]
            response = llm_result["message"]
            phone = llm_result.get("phone")
        else:
            # Tier-3: template fallback
            last_ai_msg = ""
            for msg in reversed(context):
                if msg['role'] == 'ai':
                    last_ai_msg = msg['content']
                    break
            sentiment, phone = analyze_response(response_text, last_ai_msg)
            action, response = determine_next_action(sentiment, phone, context, negotiation.stage, target="seller", missing_fields=seller_missing["missing"])

            # If counterparty asked a question, prepend acknowledgment to template
            unanswered = _detect_unanswered_question(context)
            if unanswered and response and action == 'respond':
                ack = random.choice(["понял. ", "ок. ", "да, "])
                response = ack + response

        # Safety net: regex-проверка на телефон в тексте продавца
        regex_phone = extract_phone_from_text(response_text)
        if regex_phone and action != 'warm':
            action = 'warm'
            phone = regex_phone

        logger.info(f"Переговоры {negotiation.id}: action={action}, response='{(response or '')[:30]}...', phone={phone}")

        if action == 'warm':
            deal.status = DealStatus.WARM
            deal.ai_insight = build_ai_insight(deal)
            negotiation.stage = NegotiationStage.WARM
            if phone:
                deal.seller_phone = phone
            await db.flush()
            logger.info(f">>> Сделка {deal.id} стала WARM!")
            return True

        elif action == 'close':
            deal.status = DealStatus.LOST
            deal.ai_resolution = f"Продавец отказал: {response_text[:100]}"
            negotiation.stage = NegotiationStage.CLOSED

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
            ai_msg = NegotiationMessage(
                negotiation_id=negotiation.id,
                role=MessageRole.AI,
                target=MessageTarget.SELLER,
                content=response,
            )
            db.add(ai_msg)

            outbox = OutboxMessage(
                recipient_id=negotiation.seller_sender_id or negotiation.seller_chat_id,
                message_text=response,
                status=OutboxStatus.PENDING,
                negotiation_id=negotiation.id,
            )
            db.add(outbox)

            if negotiation.stage == NegotiationStage.INITIAL:
                negotiation.stage = NegotiationStage.CONTACTED
            elif negotiation.stage == NegotiationStage.CONTACTED:
                negotiation.stage = NegotiationStage.NEGOTIATING

            deal.ai_insight = build_ai_insight(deal)

            await db.flush()
            logger.info(f">>> Переговоры {negotiation.id}: follow-up: '{response}'")
            return True

        await db.flush()
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
        deal = negotiation.deal

        # Извлекаем данные из ответа покупателя
        from src.services.message_handler import extract_price, extract_region, extract_quantity

        result_order = await db.execute(select(Order).where(Order.id == deal.buy_order_id))
        buy_order = result_order.scalar_one_or_none()

        if not deal.buy_price:
            extracted_price = extract_price(response_text)
            if extracted_price:
                deal.buy_price = extracted_price
                if buy_order:
                    buy_order.price = extracted_price
                if deal.sell_price:
                    deal.margin = extracted_price - deal.sell_price
                logger.info(f"Извлечён бюджет покупателя {extracted_price} из ответа")

        if not deal.region:
            extracted_region = extract_region(response_text)
            if extracted_region:
                deal.region = extracted_region
                if buy_order:
                    buy_order.region = extracted_region
                logger.info(f"Извлечён регион '{extracted_region}' из ответа покупателя")

        if buy_order and not buy_order.quantity:
            extracted_qty = extract_quantity(response_text)
            if extracted_qty:
                buy_order.quantity = extracted_qty
                logger.info(f"Извлечено количество '{extracted_qty}' из ответа покупателя")

        # Extract buyer preferences
        if not getattr(deal, 'buyer_preferences', None):
            extracted_prefs = _extract_preferences_from_text(response_text)
            if extracted_prefs:
                deal.buyer_preferences = extracted_prefs
                logger.info(f"Извлечены предпочтения покупателя: '{extracted_prefs[:50]}...'")

        # Collect known data and determine missing fields
        known_data = collect_known_data(deal, "buyer", context=context)
        buyer_missing = detect_missing_fields(deal, "buyer", context=context)

        # Get listing text and cross-context
        listing_text = buy_order.raw_text if buy_order else None
        cross_ctx = await build_cross_context(deal, "buyer", db)

        # Build conversation summary for LLM memory
        conversation_summary = build_conversation_summary(context)

        # Пробуем LLM, fallback на шаблоны (цена НЕ передаётся покупателю)
        llm_result = await llm.generate_negotiation_response(
            role="buyer",
            context=context,
            product=deal.product,
            price=None,
            missing_data_hint=buyer_missing["prompt_hint"],
            listing_text=listing_text,
            cross_context=cross_ctx,
            known_data=known_data,
            missing_fields=buyer_missing["missing"],
            conversation_summary=conversation_summary,
        )

        if not llm_result:
            # Tier-2: try simpler LLM call before falling back to templates
            unanswered = _detect_unanswered_question(context)
            llm_result = await llm.generate_simple_response(context, unanswered)

        if llm_result:
            action = llm_result["action"]
            response = llm_result["message"]
            phone = llm_result.get("phone")
        else:
            # Tier-3: template fallback
            last_ai_msg = ""
            for msg in reversed(context):
                if msg['role'] == 'ai':
                    last_ai_msg = msg['content']
                    break
            sentiment, phone = analyze_response(response_text, last_ai_msg)
            action, response = determine_next_action(sentiment, phone, context, negotiation.stage, target="buyer", missing_fields=buyer_missing["missing"])

            # If counterparty asked a question, prepend acknowledgment to template
            unanswered = _detect_unanswered_question(context)
            if unanswered and response and action == 'respond':
                ack = random.choice(["понял. ", "ок. ", "да, "])
                response = ack + response

        # Safety net: regex-проверка на телефон
        regex_phone = extract_phone_from_text(response_text)
        if regex_phone and action != 'warm':
            action = 'warm'
            phone = regex_phone

        logger.info(f"Переговоры {negotiation.id} (покупатель): action={action}, response='{(response or '')[:30]}...', phone={phone}")

        if action == 'warm' and phone:
            deal.ai_insight = build_ai_insight(deal)
            deal.buyer_phone = phone
            await db.flush()
            logger.info(f">>> Сделка {deal.id}: покупатель дал номер!")
            return True

        elif action == 'close':
            deal.ai_insight = build_ai_insight(deal)

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
            ai_msg = NegotiationMessage(
                negotiation_id=negotiation.id,
                role=MessageRole.AI,
                target=MessageTarget.BUYER,
                content=response,
            )
            db.add(ai_msg)

            outbox = OutboxMessage(
                recipient_id=deal.buyer_sender_id or deal.buyer_chat_id,
                message_text=response,
                status=OutboxStatus.PENDING,
                negotiation_id=negotiation.id,
            )
            db.add(outbox)

            deal.ai_insight = build_ai_insight(deal)

            await db.flush()
            logger.info(f">>> Переговоры {negotiation.id}: follow-up покупателю: '{response}'")
            return True

        deal.ai_insight = build_ai_insight(deal)
        await db.flush()
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
