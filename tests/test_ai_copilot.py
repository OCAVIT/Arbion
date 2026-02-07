"""
Tests for AI Copilot (Section 4):
- get_ai_mode returns correct defaults
- _should_ai_respond respects ai_mode
- AICopilot.build_market_context
- AICopilot.recalculate_margin
- initiate_negotiation branches on ai_mode
"""

import os
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Set required env vars before importing src modules
os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

from src.services.ai_copilot import get_ai_mode, AICopilot
from src.services.message_handler import _should_ai_respond, NegotiationStage


# =====================================================
# Helper: fake objects
# =====================================================

def _make_negotiation(stage=NegotiationStage.INITIAL, seller_phone=None, buyer_phone=None):
    """Create a fake negotiation-like object."""
    deal = SimpleNamespace(seller_phone=seller_phone, buyer_phone=buyer_phone)
    return SimpleNamespace(stage=stage, deal=deal)


# =====================================================
# Tests: _should_ai_respond with ai_mode
# =====================================================

class TestShouldAiRespondWithMode:
    def test_copilot_mode_always_silent(self):
        neg = _make_negotiation(stage=NegotiationStage.INITIAL)
        assert _should_ai_respond(neg, "seller", ai_mode="copilot") is False

    def test_copilot_mode_silent_even_negotiating(self):
        neg = _make_negotiation(stage=NegotiationStage.NEGOTIATING)
        assert _should_ai_respond(neg, "seller", ai_mode="copilot") is False

    def test_copilot_mode_silent_for_buyer(self):
        neg = _make_negotiation(stage=NegotiationStage.CONTACTED)
        assert _should_ai_respond(neg, "buyer", ai_mode="copilot") is False

    def test_autopilot_mode_responds(self):
        neg = _make_negotiation(stage=NegotiationStage.INITIAL)
        assert _should_ai_respond(neg, "seller", ai_mode="autopilot") is True

    def test_default_mode_responds(self):
        """Without ai_mode parameter, defaults to autopilot (backward compat)."""
        neg = _make_negotiation(stage=NegotiationStage.INITIAL)
        assert _should_ai_respond(neg, "seller") is True

    def test_autopilot_closed_still_silent(self):
        neg = _make_negotiation(stage=NegotiationStage.CLOSED)
        assert _should_ai_respond(neg, "seller", ai_mode="autopilot") is False

    def test_autopilot_warm_seller_with_phone_silent(self):
        neg = _make_negotiation(stage=NegotiationStage.WARM, seller_phone="+79991234567")
        assert _should_ai_respond(neg, "seller", ai_mode="autopilot") is False

    def test_autopilot_warm_buyer_no_phone_responds(self):
        neg = _make_negotiation(stage=NegotiationStage.WARM, seller_phone="+79991234567")
        assert _should_ai_respond(neg, "buyer", ai_mode="autopilot") is True


# =====================================================
# Tests: get_ai_mode
# =====================================================

class TestGetAiMode:
    @pytest.mark.asyncio
    async def test_default_copilot(self, db_session):
        """With no setting in DB, default should be 'copilot'."""
        mode = await get_ai_mode(db_session)
        assert mode == "copilot"

    @pytest.mark.asyncio
    async def test_explicit_autopilot(self, db_session):
        """When ai_mode is set to 'autopilot', return that."""
        from src.models import SystemSetting
        setting = SystemSetting(key="ai_mode", value={"v": "autopilot"})
        db_session.add(setting)
        await db_session.flush()

        mode = await get_ai_mode(db_session)
        assert mode == "autopilot"

    @pytest.mark.asyncio
    async def test_explicit_copilot(self, db_session):
        """When ai_mode is set to 'copilot', return that."""
        from src.models import SystemSetting
        setting = SystemSetting(key="ai_mode", value={"v": "copilot"})
        db_session.add(setting)
        await db_session.flush()

        mode = await get_ai_mode(db_session)
        assert mode == "copilot"

    @pytest.mark.asyncio
    async def test_invalid_value_defaults_copilot(self, db_session):
        """Unknown ai_mode value should default to 'copilot'."""
        from src.models import SystemSetting
        setting = SystemSetting(key="ai_mode", value={"v": "unknown_mode"})
        db_session.add(setting)
        await db_session.flush()

        mode = await get_ai_mode(db_session)
        assert mode == "copilot"


# =====================================================
# Tests: AICopilot.build_market_context
# =====================================================

class TestBuildMarketContext:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty(self, db_session):
        """With no orders in DB, return empty context."""
        copilot = AICopilot()
        ctx = await copilot.build_market_context("арматура", "стройматериалы", db_session)
        assert ctx["sources_count"] == 0
        assert ctx["avg_price"] is None

    @pytest.mark.asyncio
    async def test_with_orders(self, db_session):
        """With matching orders, return price statistics."""
        from src.models import Order, OrderType

        # Create some orders with prices
        for price in [45000, 48000, 50000]:
            order = Order(
                order_type=OrderType.SELL,
                chat_id=100,
                sender_id=200,
                message_id=price,  # unique
                product="арматура а500с",
                price=Decimal(str(price)),
                raw_text=f"продам арматуру {price}",
                niche="стройматериалы",
                platform="telegram",
            )
            db_session.add(order)
        await db_session.flush()

        copilot = AICopilot()
        ctx = await copilot.build_market_context("арматура", "стройматериалы", db_session)
        assert ctx["sources_count"] == 3
        assert ctx["min_seen"] == 45000
        assert ctx["max_seen"] == 50000
        assert 47000 <= ctx["avg_price"] <= 48000


# =====================================================
# Tests: AICopilot.recalculate_margin
# =====================================================

class TestRecalculateMargin:
    @pytest.mark.asyncio
    async def test_sell_price_change(self, db_session):
        """Recalculate margin when sell price changes."""
        from src.models import DetectedDeal, DealStatus, Order, OrderType

        # Create orders first
        buy_order = Order(
            order_type=OrderType.BUY, chat_id=1, sender_id=1, message_id=1,
            product="цемент", price=Decimal("55000"), raw_text="куплю цемент",
            platform="telegram",
        )
        sell_order = Order(
            order_type=OrderType.SELL, chat_id=2, sender_id=2, message_id=2,
            product="цемент", price=Decimal("50000"), raw_text="продам цемент",
            platform="telegram",
        )
        db_session.add_all([buy_order, sell_order])
        await db_session.flush()

        deal = DetectedDeal(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            product="цемент",
            buy_price=Decimal("55000"),
            sell_price=Decimal("50000"),
            margin=Decimal("5000"),
            status=DealStatus.COLD,
            lead_source="system",
            deal_model="agency",
            buyer_payment_status="pending",
            seller_payment_status="pending",
            our_commission_status="pending",
            platform="telegram",
        )
        db_session.add(deal)
        await db_session.flush()

        copilot = AICopilot()
        result = await copilot.recalculate_margin(deal.id, 48000, "sell", db_session)
        assert result["new_margin"] == 7000  # 55000 - 48000
        assert result["old_margin"] == 5000
        assert "выросла" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_deal_not_found(self, db_session):
        copilot = AICopilot()
        result = await copilot.recalculate_margin(99999, 50000, "sell", db_session)
        assert "error" in result


# =====================================================
# Tests: initiate_negotiation copilot branch
# =====================================================

class TestInitiateNegotiationCopilot:
    @pytest.mark.asyncio
    async def test_copilot_generates_draft(self, db_session):
        """In copilot mode, initiate_negotiation should generate a draft, not send."""
        from src.models import DetectedDeal, DealStatus, Order, OrderType, SystemSetting

        # Set copilot mode
        setting = SystemSetting(key="ai_mode", value={"v": "copilot"})
        db_session.add(setting)

        # Create orders
        buy_order = Order(
            order_type=OrderType.BUY, chat_id=10, sender_id=10, message_id=10,
            product="арматура", price=Decimal("52000"), raw_text="куплю арматуру",
            platform="telegram",
        )
        sell_order = Order(
            order_type=OrderType.SELL, chat_id=20, sender_id=20, message_id=20,
            product="арматура", price=Decimal("47000"), raw_text="продам арматуру",
            platform="telegram",
        )
        db_session.add_all([buy_order, sell_order])
        await db_session.flush()

        deal = DetectedDeal(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            product="арматура",
            buy_price=Decimal("52000"),
            sell_price=Decimal("47000"),
            margin=Decimal("5000"),
            status=DealStatus.COLD,
            buyer_chat_id=10,
            buyer_sender_id=10,
            lead_source="system",
            deal_model="agency",
            buyer_payment_status="pending",
            seller_payment_status="pending",
            our_commission_status="pending",
            platform="telegram",
        )
        db_session.add(deal)
        await db_session.flush()

        # Mock LLM to return a draft
        with patch("src.services.llm.generate_initial_message", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "привет, арматура ещё актуальна?"

            from src.services.ai_negotiator import initiate_negotiation
            result = await initiate_negotiation(deal, db_session)

        # Should return None (no Negotiation created)
        assert result is None
        # Draft should be saved
        assert deal.ai_draft_message == "привет, арматура ещё актуальна?"
        # Market context should be JSON
        assert deal.market_price_context is not None
        ctx = json.loads(deal.market_price_context)
        assert "sources_count" in ctx
        # Status should remain COLD
        assert deal.status == DealStatus.COLD

    @pytest.mark.asyncio
    async def test_copilot_skips_existing_draft(self, db_session):
        """If deal already has a draft, copilot should skip it."""
        from src.models import DetectedDeal, DealStatus, Order, OrderType, SystemSetting

        setting = SystemSetting(key="ai_mode", value={"v": "copilot"})
        db_session.add(setting)

        buy_order = Order(
            order_type=OrderType.BUY, chat_id=10, sender_id=10, message_id=100,
            product="цемент", price=Decimal("30000"), raw_text="куплю цемент",
            platform="telegram",
        )
        sell_order = Order(
            order_type=OrderType.SELL, chat_id=20, sender_id=20, message_id=200,
            product="цемент", price=Decimal("25000"), raw_text="продам цемент",
            platform="telegram",
        )
        db_session.add_all([buy_order, sell_order])
        await db_session.flush()

        deal = DetectedDeal(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            product="цемент",
            buy_price=Decimal("30000"),
            sell_price=Decimal("25000"),
            margin=Decimal("5000"),
            status=DealStatus.COLD,
            ai_draft_message="existing draft",
            lead_source="system",
            deal_model="agency",
            buyer_payment_status="pending",
            seller_payment_status="pending",
            our_commission_status="pending",
            platform="telegram",
        )
        db_session.add(deal)
        await db_session.flush()

        from src.services.ai_negotiator import initiate_negotiation
        result = await initiate_negotiation(deal, db_session)

        assert result is None
        assert deal.ai_draft_message == "existing draft"  # Not overwritten

    @pytest.mark.asyncio
    async def test_autopilot_creates_negotiation(self, db_session):
        """In autopilot mode, initiate_negotiation should create Negotiation and outbox."""
        from src.models import (
            DetectedDeal, DealStatus, Order, OrderType,
            SystemSetting, Negotiation, OutboxMessage,
        )
        from sqlalchemy import select

        setting = SystemSetting(key="ai_mode", value={"v": "autopilot"})
        db_session.add(setting)

        buy_order = Order(
            order_type=OrderType.BUY, chat_id=30, sender_id=30, message_id=30,
            product="щебень", price=Decimal("2000"), raw_text="куплю щебень",
            platform="telegram",
        )
        sell_order = Order(
            order_type=OrderType.SELL, chat_id=40, sender_id=40, message_id=40,
            product="щебень", price=Decimal("1500"), raw_text="продам щебень",
            platform="telegram",
        )
        db_session.add_all([buy_order, sell_order])
        await db_session.flush()

        deal = DetectedDeal(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            product="щебень",
            buy_price=Decimal("2000"),
            sell_price=Decimal("1500"),
            margin=Decimal("500"),
            status=DealStatus.COLD,
            buyer_chat_id=30,
            buyer_sender_id=30,
            lead_source="system",
            deal_model="agency",
            buyer_payment_status="pending",
            seller_payment_status="pending",
            our_commission_status="pending",
            platform="telegram",
        )
        db_session.add(deal)
        await db_session.flush()

        with patch("src.services.llm.generate_initial_message", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "привет, щебень ещё есть?"

            from src.services.ai_negotiator import initiate_negotiation
            result = await initiate_negotiation(deal, db_session)

        # Should create Negotiation
        assert result is not None
        assert isinstance(result, Negotiation)
        # Status should change to IN_PROGRESS
        assert deal.status == DealStatus.IN_PROGRESS
        # Outbox messages should be created
        outbox_result = await db_session.execute(
            select(OutboxMessage).where(OutboxMessage.negotiation_id == result.id)
        )
        outbox_msgs = outbox_result.scalars().all()
        assert len(outbox_msgs) >= 1
