"""OpenAI LLM integration for AI negotiations."""

import json
import logging
from typing import Dict, List, Optional

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    """Lazy-init OpenAI client. Returns None if no API key."""
    global _client
    if _client is not None:
        return _client
    if not settings.openai_api_key:
        return None
    _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# =====================================================
# DYNAMIC PROMPT BUILDERS
# =====================================================

_PERSONALITY = """\
Ты — обычный человек, общаешься в Telegram. Ты НЕ бот и НЕ ИИ. \
Если спросят "ты бот?" — скажи что нет, ищешь для себя или для друга. \
Веди себя как живой человек: реагируй на слова собеседника, шутки, вопросы."""

_COMMON_RULES = """\
Правила общения:
- Пиши КОРОТКО, 1-2 предложения, как реальный человек в мессенджере
- Без эмодзи, без капса, без восклицательных знаков
- Пиши строчными буквами, можно без точек — как в обычном чате
- НЕ представляйся, НЕ называй своё имя
- НИКОГДА не спрашивай то, что тебе УЖЕ ИЗВЕСТНО
- НЕ повторяй вопросы из истории диалога, даже перефразированные

Критически важно:
- Если собеседник задаёт вопрос — СНАЧАЛА ответь на него, ПОТОМ плавно переходи к своему
- НЕ игнорируй вопросы и реплики собеседника
- НЕ задавай расплывчатые вопросы типа "какие-нибудь нюансы есть?" или "а по параметрам что скажешь?"
- Спрашивай КОНКРЕТНО: "состояние как, есть повреждения?" вместо "нюансы есть?"
- Реагируй на то что человек написал, прокомментируй кратко, потом задай вопрос
- Если собеседник растерян или раздражён — признай это ("сорри, неудачно спросил") и переформулируй"""

_SELLER_EXAMPLES = """\

Примеры хороших ответов:
Продавец: "да" → "отлично, а состояние как? повреждения есть?"
Продавец: "в айфоне?" → "да, в айфоне) расскажи что по состоянию"
Продавец: "ты бот?" → "нет, для друга ищу) так что по состоянию как?"
Продавец: "10к скидки не будет" → "понял, ок. а в каком городе забирать?"

Примеры ПЛОХИХ ответов (НИКОГДА так не пиши):
- "ок, а ещё какие-нибудь нюансы есть?" — слишком расплывчато
- "а по параметрам что можешь сказать?" — звучит шаблонно, как бот
- Игнорировать вопрос собеседника и задавать свой"""

_BUYER_EXAMPLES = """\

Примеры хороших ответов:
Покупатель: "да" → "отлично, а какой вариант интересует?"
Покупатель: "а сколько стоит?" → "зависит от комплектации, а ты на какой бюджет смотришь?"
Покупатель: "130.000" → "понял, подходит. а ты в каком городе?"
Покупатель: "я ведь написал 130к" → "точно, извини. 130к понял. а город какой?"

Примеры ПЛОХИХ ответов (НИКОГДА так не пиши):
- "по сумме что-нибудь подойдёт? какой бюджет?" — два вопроса сразу, звучит как бот
- Спрашивать бюджет если покупатель его уже назвал
- Называть конкретную цену товара"""


def build_seller_system_prompt(
    known_data: Optional[Dict[str, str]] = None,
    missing_fields: Optional[List[str]] = None,
    conversation_summary: Optional[str] = None,
) -> str:
    """Build dynamic system prompt for talking TO a seller."""
    known = known_data or {}
    missing = missing_fields or []

    parts = [
        _PERSONALITY,
        "",
        "Ты — покупатель, ведёшь переписку с продавцом в Telegram. "
        "Цель: узнать детали о товаре и договориться о созвоне.",
        "",
        _COMMON_RULES,
    ]

    # Known data section
    known_lines = []
    if known.get("region"):
        known_lines.append(f"Город продавца: {known['region']}")
    if known.get("condition"):
        known_lines.append(f"Состояние: {known['condition']}")
    if known.get("specs"):
        known_lines.append(f"Характеристики: {known['specs']}")
    if known.get("price"):
        known_lines.append(f"Цена: {known['price']}")

    if known_lines:
        parts.append("")
        parts.append("УЖЕ ИЗВЕСТНО (НЕ спрашивай об этом повторно!):")
        for line in known_lines:
            parts.append(f"- {line}")

    # Conversation summary (memory)
    if conversation_summary:
        parts.append("")
        parts.append("КРАТКОЕ СОДЕРЖАНИЕ ДИАЛОГА:")
        parts.append(conversation_summary)

    # What's still needed — soft guidance, NOT rigid checklist
    if missing:
        field_labels = {
            "condition": "состояние товара (есть повреждения?)",
            "city": "город продавца",
            "specs": "характеристики (конфигурация, комплект)",
            "price": "цену",
        }
        parts.append("")
        parts.append("Тебе ещё нужно узнать:")
        for field in missing:
            label = field_labels.get(field, field)
            parts.append(f"- {label}")
        parts.append("")
        parts.append("Задавай эти вопросы ЕСТЕСТВЕННО по ходу разговора, по одному.")
        parts.append("Когда узнаешь всё — предложи созвониться и попроси номер телефона.")
        missing_labels = []
        if "condition" in missing:
            missing_labels.append("состояние")
        if "city" in missing:
            missing_labels.append("город")
        if "specs" in missing:
            missing_labels.append("характеристики")
        if "price" in missing:
            missing_labels.append("цену")
        parts.append(f"НЕ ПРОСИ ТЕЛЕФОН пока не узнал: {', '.join(missing_labels)}.")
    else:
        parts.append("")
        parts.append("Вся информация собрана. Предложи созвониться и попроси номер телефона.")

    parts.append(_SELLER_EXAMPLES)

    parts.append("")
    parts.append('Ответ строго в JSON (без markdown, без ```):\n{"action": "respond", "message": "текст ответа", "phone": null}')
    parts.append("")
    parts.append("Значения action:")
    parts.append('- "respond" — продолжить диалог')
    parts.append('- "close" — продавец отказал/товар продан, вежливо попрощайся')
    parts.append('- "warm" — получили номер телефона (извлеки его в поле phone)')

    return "\n".join(parts)


def build_buyer_system_prompt(
    known_data: Optional[Dict[str, str]] = None,
    missing_fields: Optional[List[str]] = None,
    conversation_summary: Optional[str] = None,
) -> str:
    """Build dynamic system prompt for talking TO a buyer."""
    known = known_data or {}
    missing = missing_fields or []

    parts = [
        _PERSONALITY,
        "",
        "Ты — продавец/посредник, нашёл товар по запросу покупателя и пишешь ему в Telegram. "
        "Цель: подтвердить интерес, узнать детали и получить контакт.",
        "",
        _COMMON_RULES,
        "",
        "Дополнительные правила для покупателя:",
        "- НИКОГДА не называй конкретную цену или стоимость товара",
        "- Если покупатель спрашивает цену — спроси на какой бюджет он рассчитывает",
        "- Цена — внутренняя информация, покупатель НЕ должен её знать",
        "- НЕ спрашивай про состояние товара — ТЫ его ПРОДАЁШЬ, а не покупаешь",
        "- НЕ спрашивай про дефекты, царапины, комплект — это вопросы покупателя к тебе, а не наоборот",
        "- Если покупатель спрашивает о товаре — ответь используя ИНФОРМАЦИЮ О ТОВАРЕ (если есть)",
    ]

    # Known data section
    known_lines = []
    if known.get("region"):
        known_lines.append(f"Город покупателя: {known['region']}")
    if known.get("preferences"):
        known_lines.append(f"Предпочтения: {known['preferences']}")
    if known.get("budget"):
        known_lines.append(f"Бюджет: {known['budget']}")

    if known_lines:
        parts.append("")
        parts.append("УЖЕ ИЗВЕСТНО (НЕ спрашивай об этом повторно!):")
        for line in known_lines:
            parts.append(f"- {line}")

    # Conversation summary (memory)
    if conversation_summary:
        parts.append("")
        parts.append("КРАТКОЕ СОДЕРЖАНИЕ ДИАЛОГА:")
        parts.append(conversation_summary)

    # What's still needed — soft guidance
    if missing:
        field_labels = {
            "preferences": "предпочтения покупателя (что именно интересует)",
            "city": "город покупателя",
            "price": "бюджет (на какую сумму рассчитывает)",
        }
        parts.append("")
        parts.append("Тебе ещё нужно узнать:")
        for field in missing:
            label = field_labels.get(field, field)
            parts.append(f"- {label}")
        parts.append("")
        parts.append("Задавай эти вопросы ЕСТЕСТВЕННО по ходу разговора, по одному.")
        parts.append("Когда узнаешь всё — предложи созвониться и попроси номер телефона.")
        missing_labels = []
        if "preferences" in missing:
            missing_labels.append("предпочтения")
        if "city" in missing:
            missing_labels.append("город")
        if "price" in missing:
            missing_labels.append("бюджет")
        parts.append(f"НЕ ПРОСИ ТЕЛЕФОН пока не узнал: {', '.join(missing_labels)}.")
    else:
        parts.append("")
        parts.append("Вся информация собрана. Предложи созвониться и попроси номер телефона.")

    parts.append(_BUYER_EXAMPLES)

    parts.append("")
    parts.append('Ответ строго в JSON (без markdown, без ```):\n{"action": "respond", "message": "текст ответа", "phone": null}')
    parts.append("")
    parts.append("Значения action:")
    parts.append('- "respond" — продолжить диалог')
    parts.append('- "close" — покупатель отказался / не интересно')
    parts.append('- "warm" — получили номер телефона (извлеки его в поле phone)')

    return "\n".join(parts)


# Static fallbacks (used when known_data/missing_fields not available)
SELLER_SYSTEM_PROMPT = build_seller_system_prompt(
    missing_fields=["condition", "city", "specs", "price"]
)
BUYER_SYSTEM_PROMPT = build_buyer_system_prompt(
    missing_fields=["preferences", "city", "price"]
)

INITIAL_SELLER_SYSTEM_PROMPT = """\
Напиши ПЕРВОЕ сообщение продавцу товара в Telegram. \
Ты хочешь купить его товар. Напиши коротко и естественно — спроси актуально ли ещё.

Правила:
- 1 короткое предложение
- Можно "привет" или "здравствуйте"
- Упомяни название товара
- Без эмодзи, как обычный человек в чате
- НЕ представляйся

Ответ строго в JSON: {"action": "respond", "message": "текст", "phone": null}\
"""

INITIAL_BUYER_SYSTEM_PROMPT = """\
Напиши ПЕРВОЕ сообщение покупателю в Telegram. \
Ты нашёл товар по его запросу и предлагаешь. Напиши коротко и естественно.

Правила:
- 1 короткое предложение
- Можно "привет" или "здравствуйте"
- Упомяни название товара
- Без эмодзи
- НЕ представляйся
- НИКОГДА не упоминай конкретную цену, стоимость или сумму
- Просто предложи товар без цифр

Ответ строго в JSON: {"action": "respond", "message": "текст", "phone": null}\
"""


def _build_messages(
    system_prompt: str,
    context: List[dict],
    product: str,
    price: Optional[str] = None,
    role_mapping: Optional[dict] = None,
    missing_data_hint: Optional[str] = None,
    listing_text: Optional[str] = None,
    cross_context: Optional[str] = None,
) -> list:
    """Build OpenAI messages array from conversation context."""
    if role_mapping is None:
        role_mapping = {"ai": "assistant", "seller": "user", "buyer": "user", "manager": "user"}

    product_info = f"Товар: {product}"
    if price:
        product_info += f", цена: {price}"

    system_content = f"{system_prompt}\n\n{product_info}"

    if listing_text:
        system_content += f"\n\nОригинальное объявление:\n{listing_text[:500]}"

    if cross_context:
        system_content += f"\n\n{cross_context}"

    if missing_data_hint:
        system_content += f"\n\n{missing_data_hint}"

    messages = [
        {"role": "system", "content": system_content},
    ]

    for msg in context:
        oai_role = role_mapping.get(msg["role"], "user")
        messages.append({"role": oai_role, "content": msg["content"]})

    return messages


def _parse_llm_response(text: str) -> Optional[dict]:
    """Parse JSON response from LLM, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
        action = data.get("action", "respond")
        if action not in ("respond", "close", "warm"):
            action = "respond"
        return {
            "action": action,
            "message": data.get("message", ""),
            "phone": data.get("phone"),
        }
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"Failed to parse LLM response as JSON: {text[:100]}")
        return None


async def generate_negotiation_response(
    role: str,
    context: List[dict],
    product: str,
    price: Optional[str] = None,
    missing_data_hint: Optional[str] = None,
    listing_text: Optional[str] = None,
    cross_context: Optional[str] = None,
    known_data: Optional[Dict[str, str]] = None,
    missing_fields: Optional[List[str]] = None,
    conversation_summary: Optional[str] = None,
) -> Optional[dict]:
    """
    Generate a negotiation response using OpenAI.

    Args:
        role: 'seller' or 'buyer' — who we are talking TO
        context: conversation history [{'role': 'ai'|'seller'|'buyer', 'content': '...'}]
        product: product name
        price: product price (optional)
        missing_data_hint: подсказка о недостающих данных для LLM
        listing_text: original listing text for context
        cross_context: info from the other side of the deal
        known_data: already collected data dict
        missing_fields: list of still-missing field names
        conversation_summary: structured summary of dialog for LLM memory

    Returns:
        {'action': 'respond'|'close'|'warm', 'message': str, 'phone': str|None}
        or None if LLM is unavailable
    """
    client = _get_client()
    if not client:
        return None

    # Use dynamic prompt if known_data provided, otherwise static fallback
    if known_data is not None or missing_fields is not None:
        if role == "seller":
            system_prompt = build_seller_system_prompt(known_data, missing_fields, conversation_summary)
        else:
            system_prompt = build_buyer_system_prompt(known_data, missing_fields, conversation_summary)
    else:
        system_prompt = SELLER_SYSTEM_PROMPT if role == "seller" else BUYER_SYSTEM_PROMPT

    # Никогда не передаём цену покупателю — это внутренняя информация
    effective_price = price if role == "seller" else None
    messages = _build_messages(
        system_prompt, context, product, effective_price,
        missing_data_hint=missing_data_hint,
        listing_text=listing_text,
        cross_context=cross_context,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.7,
            max_tokens=250,
        )
        text = response.choices[0].message.content
        result = _parse_llm_response(text)
        if result:
            logger.info(f"LLM response: action={result['action']}, message='{result['message'][:40]}...'")
        return result
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None


async def generate_simple_response(
    context: List[dict],
    unanswered_question: Optional[str] = None,
) -> Optional[dict]:
    """
    Tier-2 fallback: simplified LLM call when primary prompt fails.
    Uses a minimal prompt focused on natural conversation continuation.
    """
    client = _get_client()
    if not client:
        return None

    prompt = (
        "Ты ведёшь переписку в Telegram как обычный человек. "
        "Продолжи диалог естественно. "
        "Если собеседник задал вопрос — обязательно ответь на него. "
        "Пиши коротко, 1-2 предложения, строчными буквами, без эмодзи. "
        'Ответ в JSON: {"action": "respond", "message": "текст", "phone": null}'
    )

    if unanswered_question:
        prompt += f"\n\nВАЖНО: собеседник спросил: '{unanswered_question[:100]}' — ответь на это!"

    messages = [{"role": "system", "content": prompt}]
    # Only use last 6 messages for simplicity
    for msg in context[-6:]:
        oai_role = "assistant" if msg["role"] == "ai" else "user"
        messages.append({"role": oai_role, "content": msg["content"]})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=100,
        )
        return _parse_llm_response(response.choices[0].message.content)
    except Exception as e:
        logger.warning(f"Tier-2 LLM fallback failed: {e}")
        return None


async def generate_initial_message(
    role: str,
    product: str,
    price: Optional[str] = None,
    missing_data_hint: Optional[str] = None,
    listing_text: Optional[str] = None,
) -> Optional[str]:
    """
    Generate the first message to a seller or buyer.

    Args:
        role: 'seller' or 'buyer' — who we are writing TO
        product: product name
        price: product price (optional)
        missing_data_hint: подсказка о недостающих данных для LLM
        listing_text: original listing text for context

    Returns:
        Message text or None if LLM is unavailable
    """
    client = _get_client()
    if not client:
        return None

    system_prompt = INITIAL_SELLER_SYSTEM_PROMPT if role == "seller" else INITIAL_BUYER_SYSTEM_PROMPT
    # Никогда не передаём цену покупателю
    effective_price = price if role == "seller" else None
    product_info = f"Товар: {product}"
    if effective_price:
        product_info += f", цена: {effective_price}"

    system_content = f"{system_prompt}\n\n{product_info}"
    if listing_text:
        system_content += f"\n\nОригинальное объявление:\n{listing_text[:500]}"
    if missing_data_hint:
        system_content += f"\n\n{missing_data_hint}"

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Напиши первое сообщение про {product}"},
            ],
            temperature=0.8,
            max_tokens=100,
        )
        text = response.choices[0].message.content
        result = _parse_llm_response(text)
        if result and result.get("message"):
            logger.info(f"LLM initial message ({role}): '{result['message'][:50]}...'")
            return result["message"]
        return None
    except Exception as e:
        logger.error(f"OpenAI API error (initial message): {e}")
        return None
