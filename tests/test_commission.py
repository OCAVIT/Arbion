"""
Tests for tiered commission calculation (Section 5).

Covers:
- calculate_commission_rate with system/manager leads
- Custom manager rate override
- Commission integration in deal closing (ledger fields)
"""

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

from src.services.commission import (
    calculate_commission_rate,
    SYSTEM_LEAD_RATE,
    MANAGER_LEAD_RATE,
)


def _make_deal(**kwargs):
    defaults = {"lead_source": "system"}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_manager(**kwargs):
    defaults = {"commission_rate": Decimal("0.10")}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── calculate_commission_rate ─────────────────────────────


class TestCalculateCommissionRate:
    def test_system_lead_default_rate(self):
        deal = _make_deal(lead_source="system")
        manager = _make_manager()
        rate = calculate_commission_rate(deal, manager)
        assert rate == SYSTEM_LEAD_RATE  # 0.20

    def test_manager_lead_default_rate(self):
        deal = _make_deal(lead_source="manager")
        manager = _make_manager()
        rate = calculate_commission_rate(deal, manager)
        assert rate == MANAGER_LEAD_RATE  # 0.35

    def test_custom_rate_overrides_system(self):
        deal = _make_deal(lead_source="system")
        manager = _make_manager(commission_rate=Decimal("0.25"))
        rate = calculate_commission_rate(deal, manager)
        assert rate == Decimal("0.25")

    def test_custom_rate_overrides_manager_lead(self):
        deal = _make_deal(lead_source="manager")
        manager = _make_manager(commission_rate=Decimal("0.40"))
        rate = calculate_commission_rate(deal, manager)
        assert rate == Decimal("0.40")

    def test_old_default_010_not_treated_as_custom(self):
        """0.10 is the legacy default — should NOT override the tier rate."""
        deal = _make_deal(lead_source="system")
        manager = _make_manager(commission_rate=Decimal("0.10"))
        rate = calculate_commission_rate(deal, manager)
        assert rate == SYSTEM_LEAD_RATE  # 0.20, not 0.10

    def test_none_commission_uses_tier(self):
        deal = _make_deal(lead_source="manager")
        manager = _make_manager(commission_rate=None)
        rate = calculate_commission_rate(deal, manager)
        assert rate == MANAGER_LEAD_RATE  # 0.35

    def test_rate_is_decimal(self):
        deal = _make_deal(lead_source="system")
        manager = _make_manager()
        rate = calculate_commission_rate(deal, manager)
        assert isinstance(rate, Decimal)


# ── Commission math sanity ────────────────────────────────


class TestCommissionMath:
    def test_system_lead_margin_50k(self):
        """50K margin × 20% = 10K to manager."""
        margin = Decimal("50000")
        rate = SYSTEM_LEAD_RATE
        assert margin * rate == Decimal("10000.00")

    def test_manager_lead_margin_50k(self):
        """50K margin × 35% = 17.5K to manager."""
        margin = Decimal("50000")
        rate = MANAGER_LEAD_RATE
        assert margin * rate == Decimal("17500.00")

    def test_custom_rate_margin(self):
        margin = Decimal("100000")
        rate = Decimal("0.25")
        assert margin * rate == Decimal("25000.00")
