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

_COMMON_RULES = """\
Правила общения:
- Пиши КОРОТКО, 1-2 предложения максимум, как реальный человек в мессенджере
- Без эмодзи, без капса, без восклицательных знаков
- Пиши строчными буквами, можно без точек — как в обычном чате
- НЕ представляйся, НЕ называй своё имя
- НЕ говори что ты бот или ИИ
- НИКОГДА не спрашивай то, что тебе УЖЕ ИЗВЕСТНО
- НЕ повторяй вопросы, которые уже были в диалоге"""


def build_seller_system_prompt(
    known_data: Optional[Dict[str, str]] = None,
    missing_fields: Optional[List[str]] = None,
) -> str:
    """Build dynamic system prompt for talking TO a seller."""
    known = known_data or {}
    missing = missing_fields or []

    parts = [
        "Ты — заинтересованный покупатель, ведёшь переписку в Telegram. "
        "Твоя задача: узнать максимум информации о товаре и только после этого получить номер телефона для созвона.",
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
        parts.append("УЖЕ ИЗВЕСТНО (НЕ спрашивай об этом):")
        for line in known_lines:
            parts.append(f"- {line}")

    # Dynamic strategy — only missing fields
    strategy_steps = []
    step = 1
    if "condition" in missing:
        strategy_steps.append(f"{step}. Узнай состояние товара (дефекты, нюансы)")
        step += 1
    if "city" in missing:
        strategy_steps.append(f"{step}. Узнай город продавца")
        step += 1
    if "specs" in missing:
        strategy_steps.append(f"{step}. Узнай основные характеристики товара")
        step += 1
    if "price" in missing:
        strategy_steps.append(f"{step}. Обсуди цену (попроси скидку если уместно)")
        step += 1

    if strategy_steps:
        parts.append("")
        parts.append("Стратегия (СТРОГО по порядку, спрашивай по одному):")
        parts.extend(strategy_steps)
        parts.append(f"{step}. ТОЛЬКО ПОСЛЕ всего вышеперечисленного — попроси номер телефона")
        parts.append("")
        missing_labels = []
        if "condition" in missing:
            missing_labels.append("состояние")
        if "city" in missing:
            missing_labels.append("город")
        if "specs" in missing:
            missing_labels.append("характеристики")
        if "price" in missing:
            missing_labels.append("цену")
        parts.append(f"ОБЯЗАТЕЛЬНО — НЕ ПРОСИ ТЕЛЕФОН пока не узнал: {', '.join(missing_labels)}.")
    else:
        parts.append("")
        parts.append("Вся необходимая информация собрана — можешь попросить номер телефона для созвона.")

    parts.append("")
    parts.append('Ответ строго в JSON (без markdown, без ```):\n{"action": "respond", "message": "текст ответа", "phone": null}')
    parts.append("")
    parts.append("Значения action:")
    parts.append('- "respond" — продолжить диалог (написать сообщение)')
    parts.append('- "close" — продавец отказал/товар продан, вежливо прощаемся')
    parts.append('- "warm" — получили номер телефона (извлеки его в поле phone)')

    return "\n".join(parts)


def build_buyer_system_prompt(
    known_data: Optional[Dict[str, str]] = None,
    missing_fields: Optional[List[str]] = None,
) -> str:
    """Build dynamic system prompt for talking TO a buyer."""
    known = known_data or {}
    missing = missing_fields or []

    parts = [
        "Ты — продавец/посредник, нашёл товар по запросу покупателя и пишешь ему в Telegram. "
        "Твоя задача: подтвердить интерес, узнать детали и только потом получить контакт.",
        "",
        _COMMON_RULES,
        "- НИКОГДА не называй конкретную цену или стоимость товара",
        "- Если покупатель спрашивает цену — спроси на какой бюджет он рассчитывает",
        "- Цена — это внутренняя информация, покупатель НЕ должен её знать",
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
        parts.append("УЖЕ ИЗВЕСТНО (НЕ спрашивай об этом):")
        for line in known_lines:
            parts.append(f"- {line}")

    # Dynamic strategy — only missing fields
    strategy_steps = []
    step = 1
    if "preferences" in missing:
        strategy_steps.append(f"{step}. Узнай предпочтения покупателя (что именно интересует)")
        step += 1
    if "city" in missing:
        strategy_steps.append(f"{step}. Узнай город покупателя")
        step += 1
    if "price" in missing:
        strategy_steps.append(f"{step}. Узнай бюджет (на какую сумму рассчитывает)")
        step += 1

    if strategy_steps:
        parts.append("")
        parts.append("Стратегия (СТРОГО по порядку, спрашивай по одному):")
        parts.extend(strategy_steps)
        parts.append(f"{step}. ТОЛЬКО ПОСЛЕ всего вышеперечисленного — попроси номер телефона")
        parts.append("")
        missing_labels = []
        if "preferences" in missing:
            missing_labels.append("предпочтения")
        if "city" in missing:
            missing_labels.append("город")
        if "price" in missing:
            missing_labels.append("бюджет")
        parts.append(f"ОБЯЗАТЕЛЬНО — НЕ ПРОСИ ТЕЛЕФОН пока не узнал: {', '.join(missing_labels)}.")
    else:
        parts.append("")
        parts.append("Вся необходимая информация собрана — можешь попросить номер телефона для связи.")

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
            system_prompt = build_seller_system_prompt(known_data, missing_fields)
        else:
            system_prompt = build_buyer_system_prompt(known_data, missing_fields)
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
            max_tokens=200,
        )
        text = response.choices[0].message.content
        result = _parse_llm_response(text)
        if result:
            logger.info(f"LLM response: action={result['action']}, message='{result['message'][:40]}...'")
        return result
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
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
