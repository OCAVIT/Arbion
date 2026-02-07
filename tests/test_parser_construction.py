"""
Tests for the construction materials parser (Section 3).

Tests all 9 user-provided messages to verify:
- Order type detection (buy/sell)
- Product extraction
- Niche detection
- Price extraction
- Volume extraction
- Region extraction
"""

import os
import sys
from decimal import Decimal

# Set required env var before importing src modules
os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

from src.services.message_handler import (
    detect_order_type,
    extract_price,
    extract_product,
    extract_region,
    extract_volume,
    _products_match,
    _normalize_product,
)
from src.models.order import OrderType


# =====================================================
# SELL messages
# =====================================================

class TestSellMessage1:
    """Продаю арматуру А500С д12, 47000р/тн, от 20 тонн, склад Тула"""

    text = "Продаю арматуру А500С д12, 47000р/тн, от 20 тонн, склад Тула"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.SELL

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "арматур" in product.lower()
        assert niche == "construction"

    def test_price(self):
        price = extract_price(self.text)
        assert price is not None
        assert price == Decimal("47000")

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 20.0
        assert unit == "тонна"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Тула"


class TestSellMessage2:
    """Профнастил С21 0.5мм оцинк, 580р/м², наличие 3000м², МСК"""

    text = "Профнастил С21 0.5мм оцинк, 580р/м², наличие 3000м², МСК"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.SELL

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "профнастил" in product.lower()
        assert niche == "construction"

    def test_price(self):
        price = extract_price(self.text)
        assert price is not None
        assert price == Decimal("580")

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 3000.0
        assert unit == "м²"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Москва"


class TestSellMessage3:
    """Цемент М500 навал, 4200/тн, отгрузка с завода Воскресенск"""

    text = "Цемент М500 навал, 4200/тн, отгрузка с завода Воскресенск"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.SELL

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "цемент" in product.lower()
        assert niche == "construction"

    def test_price(self):
        price = extract_price(self.text)
        assert price is not None
        assert price == Decimal("4200")

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Воскресенск"


class TestSellMessage4:
    """Остатки бруса 150х150, 12000 руб/м³, ~15 кубов, самовывоз Подольск"""

    text = "Остатки бруса 150х150, 12000 руб/м³, ~15 кубов, самовывоз Подольск"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.SELL

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "брус" in product.lower()
        assert niche == "construction"

    def test_price(self):
        price = extract_price(self.text)
        assert price is not None
        assert price == Decimal("12000")

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 15.0
        assert unit == "м³"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Подольск"


class TestSellMessage5:
    """Реализуем щебень фр.5-20, 1850/тн, от 1 вагона"""

    text = "Реализуем щебень фр.5-20, 1850/тн, от 1 вагона"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.SELL

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "щебень" in product.lower() or "щебен" in product.lower()
        assert niche == "construction"

    def test_price(self):
        price = extract_price(self.text)
        assert price is not None
        assert price == Decimal("1850")

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 1.0
        assert unit == "вагон"


# =====================================================
# BUY messages
# =====================================================

class TestBuyMessage1:
    """Нужна арматура 10мм А500С, 40 тонн, Москва, безнал"""

    text = "Нужна арматура 10мм А500С, 40 тонн, Москва, безнал"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.BUY

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "арматур" in product.lower()
        assert niche == "construction"

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 40.0
        assert unit == "тонна"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Москва"


class TestBuyMessage2:
    """Ищу профлист С8 окрашенный, ~500м², доставка Казань"""

    text = "Ищу профлист С8 окрашенный, ~500м², доставка Казань"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.BUY

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "профлист" in product.lower()
        assert niche == "construction"

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 500.0
        assert unit == "м²"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Казань"


class TestBuyMessage3:
    """Закупаем цемент М400, объём 200 тонн/мес, нужен поставщик МСК"""

    text = "Закупаем цемент М400, объём 200 тонн/мес, нужен поставщик МСК"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.BUY

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "цемент" in product.lower()
        assert niche == "construction"

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 200.0
        assert unit == "тонна"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Москва"


class TestBuyMessage4:
    """Кто продаёт газоблок D500 600х300х200? Нужно 20 поддонов, Нижний"""

    text = "Кто продаёт газоблок D500 600х300х200? Нужно 20 поддонов, Нижний"

    def test_order_type(self):
        assert detect_order_type(self.text) == OrderType.BUY

    def test_product(self):
        product, niche = extract_product(self.text)
        assert product is not None
        assert "газоб" in product.lower() or "газоблок" in product.lower()
        assert niche == "construction"

    def test_volume(self):
        vol, unit = extract_volume(self.text)
        assert vol == 20.0
        assert unit == "поддон"

    def test_region(self):
        region = extract_region(self.text)
        assert region == "Нижний Новгород"


# =====================================================
# Product matching tests for construction materials
# =====================================================

class TestConstructionProductMatching:
    """Test that buy/sell orders for same materials match correctly."""

    def test_armatura_variants_match(self):
        assert _products_match("арматуру а500с", "арматура 10") is True

    def test_profnastil_proflist_synonym(self):
        assert _products_match("профнастил", "профлист") is True

    def test_cement_m400_m500_match(self):
        """Same product different grade should match (cement is cement)."""
        assert _products_match("цемент м400", "цемент м500") is True

    def test_gazoblock_gazobeton_synonym(self):
        assert _products_match("газоблок", "газобетон") is True

    def test_different_products_dont_match(self):
        assert _products_match("арматура", "цемент") is False

    def test_brus_variants(self):
        assert _products_match("бруса 150х150", "брус 100х100") is True


class TestNormalizeProduct:
    """Test product normalization for matching."""

    def test_remove_grade_a500s(self):
        result = _normalize_product("арматура А500С")
        assert "500" not in result

    def test_remove_grade_m500(self):
        result = _normalize_product("цемент М500")
        assert "500" not in result

    def test_remove_dimensions(self):
        result = _normalize_product("брус 150х150")
        assert "150" not in result

    def test_remove_d500(self):
        result = _normalize_product("газоблок D500")
        assert "500" not in result


# =====================================================
# Edge case tests
# =====================================================

class TestEdgeCases:
    """Edge cases for the parser."""

    def test_price_4200_per_tn(self):
        """4200/тн should be parsed as price 4200."""
        price = extract_price("цемент 4200/тн")
        assert price == Decimal("4200")

    def test_price_1850_per_tn(self):
        """1850/тн should be parsed as price 1850."""
        price = extract_price("щебень 1850/тн")
        assert price == Decimal("1850")

    def test_price_580_per_m2(self):
        """580р/м² should be parsed as price 580."""
        price = extract_price("580р/м²")
        assert price == Decimal("580")

    def test_price_47000_per_tn(self):
        """47000р/тн should be parsed as price 47000."""
        price = extract_price("47000р/тн")
        assert price == Decimal("47000")

    def test_price_12000_rub_per_m3(self):
        """12000 руб/м³ should be parsed as price 12000."""
        price = extract_price("12000 руб/м³")
        assert price == Decimal("12000")

    def test_volume_kubov(self):
        """'15 кубов' should be parsed as 15.0 м³."""
        vol, unit = extract_volume("15 кубов")
        assert vol == 15.0
        assert unit == "м³"

    def test_volume_tilde_prefix(self):
        """'~500м²' should still be parsed."""
        vol, unit = extract_volume("~500м²")
        assert vol == 500.0
        assert unit == "м²"

    def test_volume_tn_abbreviation(self):
        """'20 тн' should be parsed as тонна."""
        vol, unit = extract_volume("20 тн")
        assert vol == 20.0
        assert unit == "тонна"

    def test_nalichie_is_sell(self):
        """'наличие' alone should trigger sell detection."""
        assert detect_order_type("наличие 3000м²") == OrderType.SELL

    def test_otgruzka_s_zavoda_is_sell(self):
        """'отгрузка с завода' should trigger sell detection."""
        assert detect_order_type("отгрузка с завода") == OrderType.SELL

    def test_voskresensk_region(self):
        """Воскресенск should be recognized as a region."""
        region = extract_region("отгрузка с завода Воскресенск")
        assert region == "Воскресенск"

    def test_fr_5_20_not_volume(self):
        """'фр.5-20' should NOT be parsed as volume."""
        # This is a fraction size (5-20mm), not a volume
        vol, unit = extract_volume("фр.5-20")
        # Should either be None or not match "тонна"
        assert vol is None or unit != "тонна"

    def test_ot_prefix_small_number_not_price(self):
        """'от 1 вагона' — 1 should NOT be extracted as a price."""
        # 1 < 100 (min price), so it shouldn't be in the result
        price = extract_price("от 1 вагона")
        assert price is None

    def test_ot_20_tonn_not_price(self):
        """'от 20 тонн' — 20 should NOT be extracted as price (below 100 min)."""
        price = extract_price("от 20 тонн")
        assert price is None
