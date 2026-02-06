"""OpenAI LLM integration for AI negotiations."""

import json
import logging
from typing import List, Optional

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


SELLER_SYSTEM_PROMPT = """\
Ты — заинтересованный покупатель б/у техники, ведёшь переписку в Telegram. \
Твоя задача: узнать состояние товара, обсудить цену и получить номер телефона продавца для созвона.

Правила общения:
- Пиши КОРОТКО, 1-2 предложения максимум, как реальный человек в мессенджере
- Без эмодзи, без капса, без восклицательных знаков
- Не используй формальное обращение ("Здравствуйте", "Уважаемый") — только "привет" / "здравствуйте" в первом сообщении
- Пиши строчными буквами, можно без точек — как в обычном чате
- НЕ представляйся, НЕ называй своё имя
- НЕ говори что ты бот или ИИ

Стратегия переговоров:
1. Сначала уточни актуальность и состояние
2. Затем обсуди цену (попроси скидку если уместно)
3. В конце попроси номер телефона для созвона

Ответ строго в JSON (без markdown, без ```):
{"action": "respond", "message": "текст ответа", "phone": null}

Значения action:
- "respond" — продолжить диалог (написать сообщение)
- "close" — продавец отказал/товар продан, вежливо прощаемся
- "warm" — получили номер телефона (извлеки его в поле phone)\
"""

BUYER_SYSTEM_PROMPT = """\
Ты — продавец/посредник, нашёл товар по запросу покупателя и пишешь ему в Telegram. \
Твоя задача: подтвердить интерес покупателя, уточнить детали и получить его контакт для связи.

Правила общения:
- Пиши КОРОТКО, 1-2 предложения максимум
- Без эмодзи, без капса
- Как обычный человек в мессенджере, строчными буквами
- НЕ представляйся, НЕ называй своё имя
- НЕ говори что ты бот или ИИ

Стратегия:
1. Уточни интерес и детали (какую конфигурацию хочет, бюджет)
2. Попроси контакт для связи

Ответ строго в JSON (без markdown, без ```):
{"action": "respond", "message": "текст ответа", "phone": null}

Значения action:
- "respond" — продолжить диалог
- "close" — покупатель отказался / не интересно
- "warm" — получили номер телефона (извлеки его в поле phone)\
"""

INITIAL_SELLER_SYSTEM_PROMPT = """\
Напиши ПЕРВОЕ сообщение продавцу б/у товара в Telegram. \
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

Ответ строго в JSON: {"action": "respond", "message": "текст", "phone": null}\
"""


def _build_messages(
    system_prompt: str,
    context: List[dict],
    product: str,
    price: Optional[str] = None,
    role_mapping: Optional[dict] = None,
) -> list:
    """Build OpenAI messages array from conversation context."""
    if role_mapping is None:
        role_mapping = {"ai": "assistant", "seller": "user", "buyer": "user", "manager": "user"}

    product_info = f"Товар: {product}"
    if price:
        product_info += f", цена: {price}"

    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{product_info}"},
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
) -> Optional[dict]:
    """
    Generate a negotiation response using OpenAI.

    Args:
        role: 'seller' or 'buyer' — who we are talking TO
        context: conversation history [{'role': 'ai'|'seller'|'buyer', 'content': '...'}]
        product: product name
        price: product price (optional)

    Returns:
        {'action': 'respond'|'close'|'warm', 'message': str, 'phone': str|None}
        or None if LLM is unavailable
    """
    client = _get_client()
    if not client:
        return None

    system_prompt = SELLER_SYSTEM_PROMPT if role == "seller" else BUYER_SYSTEM_PROMPT
    messages = _build_messages(system_prompt, context, product, price)

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
) -> Optional[str]:
    """
    Generate the first message to a seller or buyer.

    Args:
        role: 'seller' or 'buyer' — who we are writing TO
        product: product name
        price: product price (optional)

    Returns:
        Message text or None if LLM is unavailable
    """
    client = _get_client()
    if not client:
        return None

    system_prompt = INITIAL_SELLER_SYSTEM_PROMPT if role == "seller" else INITIAL_BUYER_SYSTEM_PROMPT
    product_info = f"Товар: {product}"
    if price:
        product_info += f", цена: {price}"

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": f"{system_prompt}\n\n{product_info}"},
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
