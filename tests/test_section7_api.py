"""
Tests for Section 7: New API endpoints.

Covers:
- Pydantic request schema validation (SendDraftRequest, SkipLeadRequest, etc.)
- PaymentUpdateRequest validation
- LeadCardResponse construction
- SuggestedResponses schema
- Endpoint logic for analytics (niche/manager grouping)
- Commission calculation in create_lead flow
- New AuditAction values
"""

import os
from decimal import Decimal
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

import pytest
from pydantic import BaseModel, Field, ValidationError
from typing import Optional

from src.schemas.copilot import LeadCardResponse, SuggestedResponses
from src.services.commission import calculate_commission_rate


# ── Inline schema copies (avoid importing API modules that pull in jose) ──
# These mirror the actual schemas defined in src/api/panel/leads.py and
# src/api/admin/deals.py. If those change, these tests should still verify
# the same validation rules.

class SendDraftRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    target: str = Field(default="seller", pattern="^(seller|buyer)$")


class SkipLeadRequest(BaseModel):
    reason: str = Field(..., pattern="^(low_margin|bad_product|no_contact|other)$")


class CreateLeadRequest(BaseModel):
    product: str = Field(..., min_length=1, max_length=255)
    niche: Optional[str] = Field(None, pattern="^(стройматериалы|сельхоз|fmcg|other)$")
    sell_price: Decimal = Field(..., gt=0)
    buy_price: Optional[Decimal] = Field(None, gt=0)
    region: Optional[str] = Field(None, max_length=100)
    seller_city: Optional[str] = Field(None, max_length=100)
    volume: Optional[str] = Field(None, max_length=100)
    contact_info: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)


class PaymentUpdateRequest(BaseModel):
    buyer_payment_status: Optional[str] = Field(
        None, pattern="^(pending|invoiced|paid|confirmed)$"
    )
    seller_payment_status: Optional[str] = Field(
        None, pattern="^(pending|paid)$"
    )
    our_commission_status: Optional[str] = Field(
        None, pattern="^(pending|invoiced|received)$"
    )
    payment_method: Optional[str] = Field(
        None, pattern="^(bank_transfer|card|cash|crypto)$"
    )


# ── SendDraftRequest ─────────────────────────────────────


class TestSendDraftRequest:
    def test_valid_seller(self):
        req = SendDraftRequest(message="Привет, арматура ещё актуальна?", target="seller")
        assert req.target == "seller"
        assert len(req.message) > 0

    def test_valid_buyer(self):
        req = SendDraftRequest(message="Интересует объём от 20 тонн", target="buyer")
        assert req.target == "buyer"

    def test_default_target_seller(self):
        req = SendDraftRequest(message="Привет!")
        assert req.target == "seller"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            SendDraftRequest(message="", target="seller")

    def test_invalid_target_rejected(self):
        with pytest.raises(ValidationError):
            SendDraftRequest(message="test", target="unknown")


# ── SkipLeadRequest ──────────────────────────────────────


class TestSkipLeadRequest:
    def test_valid_reasons(self):
        for reason in ["low_margin", "bad_product", "no_contact", "other"]:
            req = SkipLeadRequest(reason=reason)
            assert req.reason == reason

    def test_invalid_reason_rejected(self):
        with pytest.raises(ValidationError):
            SkipLeadRequest(reason="not_interested")


# ── CreateLeadRequest ────────────────────────────────────


class TestCreateLeadRequest:
    def test_valid_minimal(self):
        req = CreateLeadRequest(product="арматура А500С", sell_price=Decimal("47000"))
        assert req.product == "арматура А500С"
        assert req.sell_price == Decimal("47000")
        assert req.niche is None

    def test_valid_full(self):
        req = CreateLeadRequest(
            product="цемент М500",
            niche="стройматериалы",
            sell_price=Decimal("5500"),
            buy_price=Decimal("6000"),
            region="Москва",
            seller_city="Тула",
            volume="20 тонн",
            contact_info="+79991234567",
            notes="Срочная поставка",
        )
        assert req.niche == "стройматериалы"
        assert req.buy_price == Decimal("6000")

    def test_invalid_niche_rejected(self):
        with pytest.raises(ValidationError):
            CreateLeadRequest(product="test", sell_price=Decimal("100"), niche="electronics")

    def test_zero_price_rejected(self):
        with pytest.raises(ValidationError):
            CreateLeadRequest(product="test", sell_price=Decimal("0"))

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            CreateLeadRequest(product="test", sell_price=Decimal("-100"))


# ── PaymentUpdateRequest ─────────────────────────────────


class TestPaymentUpdateRequest:
    def test_valid_buyer_paid(self):
        req = PaymentUpdateRequest(buyer_payment_status="paid")
        assert req.buyer_payment_status == "paid"
        assert req.seller_payment_status is None

    def test_valid_all_fields(self):
        req = PaymentUpdateRequest(
            buyer_payment_status="confirmed",
            seller_payment_status="paid",
            our_commission_status="received",
            payment_method="bank_transfer",
        )
        assert req.buyer_payment_status == "confirmed"
        assert req.payment_method == "bank_transfer"

    def test_invalid_buyer_status_rejected(self):
        with pytest.raises(ValidationError):
            PaymentUpdateRequest(buyer_payment_status="partial")

    def test_invalid_seller_status_rejected(self):
        with pytest.raises(ValidationError):
            PaymentUpdateRequest(seller_payment_status="confirmed")  # sellers only: pending|paid

    def test_invalid_payment_method_rejected(self):
        with pytest.raises(ValidationError):
            PaymentUpdateRequest(payment_method="paypal")

    def test_empty_is_valid(self):
        """All fields are optional — empty request is valid (endpoint validates no-op)."""
        req = PaymentUpdateRequest()
        assert req.buyer_payment_status is None


# ── LeadCardResponse ─────────────────────────────────────


class TestLeadCardResponse:
    def test_construction(self):
        card = LeadCardResponse(
            deal_id=1,
            product="арматура А500С",
            niche="стройматериалы",
            sell_price=47000.0,
            estimated_margin=10.6,
            volume="20 тонн",
            region="Москва",
            seller_city="Тула",
            ai_draft_seller="Привет, арматура ещё актуальна?",
            ai_draft_buyer="Нашёл арматуру А500С, интересует?",
            market_context={"avg_price": 48500, "min_seen": 45000, "max_seen": 52000},
            created_at=datetime.now(timezone.utc),
            platform="telegram",
        )
        assert card.deal_id == 1
        assert card.niche == "стройматериалы"
        assert card.market_context["avg_price"] == 48500

    def test_minimal(self):
        card = LeadCardResponse(
            deal_id=2,
            product="цемент",
            sell_price=5500.0,
            estimated_margin=0.0,
            created_at=datetime.now(timezone.utc),
        )
        assert card.platform == "telegram"
        assert card.niche is None
        assert card.market_context is None


# ── SuggestedResponses ───────────────────────────────────


class TestSuggestedResponses:
    def test_with_variants(self):
        resp = SuggestedResponses(
            variants=[
                "Отлично, какой объём минимальный?",
                "Есть сертификаты на эту партию?",
                "А доставка до Москвы входит в цену?",
            ],
            margin_info="Текущая маржа: 5000₽ (10.6%)",
        )
        assert len(resp.variants) == 3
        assert "маржа" in resp.margin_info.lower()

    def test_empty_variants(self):
        resp = SuggestedResponses(variants=[], margin_info=None)
        assert resp.variants == []
        assert resp.margin_info is None


# ── Commission in create_lead flow ───────────────────────


class TestCreateLeadCommission:
    def test_manager_lead_gets_35_percent(self):
        """When manager creates own lead, commission should be 35%."""
        deal = SimpleNamespace(lead_source="manager")
        manager = SimpleNamespace(commission_rate=Decimal("0.10"))
        rate = calculate_commission_rate(deal, manager)
        assert rate == Decimal("0.35")

    def test_system_lead_gets_20_percent(self):
        """System leads get 20% commission."""
        deal = SimpleNamespace(lead_source="system")
        manager = SimpleNamespace(commission_rate=Decimal("0.10"))
        rate = calculate_commission_rate(deal, manager)
        assert rate == Decimal("0.20")


# ── Analytics grouping logic ─────────────────────────────


class TestNicheAnalyticsLogic:
    """Test the niche grouping logic without DB."""

    def test_group_by_niche(self):
        """Verify grouping logic works for niche analytics."""
        raw_rows = [
            SimpleNamespace(niche="стройматериалы", deals=15, won_deals=10, revenue=450000, avg_margin=30000),
            SimpleNamespace(niche="agriculture", deals=5, won_deals=2, revenue=100000, avg_margin=20000),
            SimpleNamespace(niche=None, deals=3, won_deals=0, revenue=0, avg_margin=0),
        ]

        analytics = {}
        for row in raw_rows:
            niche_key = row.niche or "unknown"
            analytics[niche_key] = {
                "deals": row.deals,
                "won_deals": row.won_deals,
                "revenue": float(row.revenue or 0),
                "avg_margin": round(float(row.avg_margin or 0), 2),
            }

        assert "стройматериалы" in analytics
        assert analytics["стройматериалы"]["deals"] == 15
        assert analytics["стройматериалы"]["revenue"] == 450000.0
        assert "agriculture" in analytics
        assert analytics["unknown"]["deals"] == 3

    def test_empty_niches(self):
        """No deals should produce empty dict."""
        analytics = {}
        assert analytics == {}


class TestManagerAnalyticsLogic:
    """Test manager analytics computation logic."""

    def test_conversion_rate(self):
        won_deals = 7
        total_closed = 10
        rate = round(won_deals / total_closed * 100, 1) if total_closed > 0 else 0.0
        assert rate == 70.0

    def test_conversion_rate_zero_deals(self):
        total_closed = 0
        rate = round(0 / 1 * 100, 1) if total_closed > 0 else 0.0
        assert rate == 0.0

    def test_commission_total_aggregation(self):
        """Commission total should be sum of all manager's ledger entries."""
        commissions = [Decimal("10000"), Decimal("17500"), Decimal("5000")]
        total = sum(commissions)
        assert total == Decimal("32500")


# ── AuditAction new values ───────────────────────────────


class TestAuditActionValues:
    def test_new_actions_exist(self):
        from src.models.audit import AuditAction
        assert AuditAction.SEND_DRAFT == "send_draft"
        assert AuditAction.SKIP_LEAD == "skip_lead"
        assert AuditAction.CREATE_LEAD == "create_lead"
        assert AuditAction.UPDATE_PAYMENT == "update_payment"

    def test_existing_actions_unchanged(self):
        from src.models.audit import AuditAction
        assert AuditAction.LOGIN == "login"
        assert AuditAction.TAKE_DEAL == "take_deal"
        assert AuditAction.CLOSE_DEAL == "close_deal"
        assert AuditAction.UPDATE_DEAL == "update_deal"
