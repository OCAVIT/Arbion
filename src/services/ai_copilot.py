"""
AI Copilot — генерация подсказок для менеджера.

НЕ отправляет сообщения. Только генерирует:
- Драфт первого сообщения
- Подсказки ответов во время переговоров
- Пересчёт маржи при изменении цены
- Рыночный контекст
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DetectedDeal, Order, SystemSetting
from src.services import llm
from src.services.ai_negotiator import generate_response

logger = logging.getLogger(__name__)


async def get_ai_mode(db: AsyncSession) -> str:
    """Get AI mode from system settings.

    Returns:
        'copilot' (default) or 'autopilot'
    """
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "ai_mode")
    )
    setting = result.scalar_one_or_none()
    if setting:
        val = setting.get_value()
        if val in ("copilot", "autopilot"):
            return val
    return "copilot"


class AICopilot:
    """AI Copilot for manager assistance."""

    async def generate_initial_draft(
        self, deal: DetectedDeal, db: AsyncSession, target: str = "seller"
    ) -> str:
        """Генерирует драфт первого сообщения продавцу или покупателю.

        Формат: короткое, человечное, от первого лица.
        Привет! Арматура А500С 12мм ещё актуальна? Какой минимальный объём?

        Args:
            target: "seller" или "buyer"
        """
        if target == "seller":
            result = await db.execute(
                select(Order).where(Order.id == deal.sell_order_id)
            )
            order = result.scalar_one_or_none()
            listing_text = order.raw_text if order else None
            price_str = str(deal.sell_price) if deal.sell_price else None

            draft = await llm.generate_initial_message(
                "seller", deal.product, price_str,
                listing_text=listing_text,
            )
            if not draft:
                draft = generate_response('initial_seller', deal.product)
        else:
            result = await db.execute(
                select(Order).where(Order.id == deal.buy_order_id)
            )
            order = result.scalar_one_or_none()
            listing_text = order.raw_text if order else None

            # Never reveal price to buyer
            draft = await llm.generate_initial_message(
                "buyer", deal.product, None,
                listing_text=listing_text,
            )
            if not draft:
                draft = generate_response('initial_buyer', deal.product)

        return draft

    async def suggest_responses(
        self, negotiation_id: int, last_message: str, db: AsyncSession
    ) -> list[str]:
        """Генерирует 2-3 варианта ответа на последнее сообщение контрагента."""
        # TODO: implement when manager chat UI is ready
        return []

    async def recalculate_margin(
        self, deal_id: int, new_price: float, side: str, db: AsyncSession
    ) -> dict:
        """Пересчитывает маржу при изменении цены.

        Returns: {
            "old_margin": 3000,
            "new_margin": 3500,
            "margin_percent": 7.3,
            "recommendation": "Маржа выросла на 500₽/тонна"
        }
        """
        result = await db.execute(
            select(DetectedDeal).where(DetectedDeal.id == deal_id)
        )
        deal = result.scalar_one_or_none()
        if not deal:
            return {"error": "Deal not found"}

        old_margin = float(deal.margin or 0)

        if side == "sell":
            new_margin = float(deal.buy_price or 0) - new_price
        else:
            new_margin = new_price - float(deal.sell_price or 0)

        base_price = new_price if side == "sell" else float(deal.sell_price or 1)
        margin_pct = (new_margin / base_price * 100) if base_price else 0

        diff = new_margin - old_margin
        if diff > 0:
            rec = f"Маржа выросла на {diff:.0f}\u20bd"
        elif diff < 0:
            rec = f"Маржа упала на {abs(diff):.0f}\u20bd"
        else:
            rec = "Маржа не изменилась"

        return {
            "old_margin": old_margin,
            "new_margin": new_margin,
            "margin_percent": round(margin_pct, 1),
            "recommendation": rec,
        }

    async def build_market_context(
        self, product: str, niche: Optional[str], db: AsyncSession
    ) -> dict:
        """Собирает ценовой контекст из последних parsed messages.

        Returns: {
            "avg_price": 48500,
            "min_seen": 45000,
            "max_seen": 52000,
            "sources_count": 12,
            "trend": "stable" | "rising" | "falling"
        }
        """
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        query = (
            select(Order.price)
            .where(
                Order.price.isnot(None),
                Order.price > 0,
                Order.created_at >= week_ago,
            )
        )

        # Filter by niche if available
        if niche:
            query = query.where(Order.niche == niche)

        # Try to match product name
        if product:
            from src.services.message_handler import _normalize_product
            normalized = _normalize_product(product)
            if len(normalized) >= 3:
                query = query.where(Order.product.ilike(f"%{normalized[:10]}%"))

        result = await db.execute(query.limit(100))
        prices = [float(row[0]) for row in result.fetchall() if row[0]]

        if not prices:
            return {
                "avg_price": None,
                "min_seen": None,
                "max_seen": None,
                "sources_count": 0,
                "trend": "unknown",
            }

        avg_price = sum(prices) / len(prices)
        return {
            "avg_price": round(avg_price, 0),
            "min_seen": round(min(prices), 0),
            "max_seen": round(max(prices), 0),
            "sources_count": len(prices),
            "trend": "stable",  # TODO: trend analysis with time series
        }


# Singleton instance
copilot = AICopilot()
