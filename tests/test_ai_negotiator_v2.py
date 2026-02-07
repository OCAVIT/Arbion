"""
Unit tests for AI negotiator improvements:
- collect_known_data
- dynamic prompts (build_seller_system_prompt, build_buyer_system_prompt)
- _products_match
- _extract_preferences_from_text
- detect_missing_fields with buyer_preferences
- build_conversation_summary
- _detect_unanswered_question
- extract_price with dot-separator
"""

import os
import sys
from decimal import Decimal
from types import SimpleNamespace

# Set required env var before importing src modules
os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

from src.services.ai_negotiator import (
    collect_known_data,
    detect_missing_fields,
    _extract_preferences_from_text,
    _analyze_discussed_topics,
    build_conversation_summary,
    _detect_unanswered_question,
)
from src.services.llm import build_seller_system_prompt, build_buyer_system_prompt
from src.services.message_handler import _products_match, extract_price


# =====================================================
# Helper: fake deal object
# =====================================================

def _make_deal(**kwargs):
    """Create a fake deal-like object with given attributes."""
    defaults = {
        "region": None,
        "seller_city": None,
        "seller_condition": None,
        "seller_specs": None,
        "sell_price": None,
        "buy_price": None,
        "buyer_preferences": None,
        "sell_order": None,
        "buy_order": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# =====================================================
# Tests: collect_known_data
# =====================================================

class TestCollectKnownData:
    def test_seller_with_region(self):
        deal = _make_deal(region="Москва")
        known = collect_known_data(deal, "seller")
        assert known["region"] == "Москва"

    def test_seller_with_city_overrides_region(self):
        deal = _make_deal(region="МО", seller_city="Москва")
        known = collect_known_data(deal, "seller")
        assert known["region"] == "Москва"

    def test_seller_with_condition(self):
        deal = _make_deal(seller_condition="идеальное, без царапин")
        known = collect_known_data(deal, "seller")
        assert "condition" in known

    def test_seller_with_specs(self):
        deal = _make_deal(seller_specs="256 гб, чёрный")
        known = collect_known_data(deal, "seller")
        assert "specs" in known

    def test_seller_with_price(self):
        deal = _make_deal(sell_price=Decimal("50000"))
        known = collect_known_data(deal, "seller")
        assert known["price"] == "50000"

    def test_buyer_with_region(self):
        deal = _make_deal(region="СПб")
        known = collect_known_data(deal, "buyer")
        assert known["region"] == "СПб"

    def test_buyer_with_preferences(self):
        deal = _make_deal(buyer_preferences="чёрный, 128гб")
        known = collect_known_data(deal, "buyer")
        assert known["preferences"] == "чёрный, 128гб"

    def test_buyer_with_budget(self):
        deal = _make_deal(buy_price=Decimal("60000"))
        known = collect_known_data(deal, "buyer")
        assert known["budget"] == "60000"

    def test_empty_deal(self):
        deal = _make_deal()
        known = collect_known_data(deal, "seller")
        assert known == {}

    def test_context_scanning_for_region(self):
        deal = _make_deal()
        context = [
            {"role": "ai", "content": "а ты в каком городе?"},
            {"role": "seller", "content": "москва, могу встретиться"},
        ]
        known = collect_known_data(deal, "seller", context=context)
        assert known.get("region") == "Москва"


# =====================================================
# Tests: build_seller_system_prompt
# =====================================================

class TestBuildSellerSystemPrompt:
    def test_known_region_not_in_missing(self):
        prompt = build_seller_system_prompt(
            known_data={"region": "Москва"},
            missing_fields=["condition", "specs"],
        )
        assert "Москва" in prompt
        # "город продавца" should only appear in the "known" section, not in the "need to learn" section
        need_section = prompt.lower().split("нужно узнать")[-1] if "нужно узнать" in prompt.lower() else ""
        assert "город" not in need_section.split("примеры")[0]

    def test_all_known_ask_phone(self):
        prompt = build_seller_system_prompt(
            known_data={"region": "Москва", "condition": "идеал", "specs": "128гб", "price": "50000"},
            missing_fields=[],
        )
        assert "номер телефона" in prompt
        assert "НЕ ПРОСИ ТЕЛЕФОН" not in prompt

    def test_missing_condition_in_prompt(self):
        prompt = build_seller_system_prompt(
            known_data={},
            missing_fields=["condition", "city"],
        )
        assert "состояние" in prompt.lower()
        assert "город" in prompt.lower()

    def test_no_electronics_specific_text(self):
        prompt = build_seller_system_prompt(
            known_data={},
            missing_fields=["condition"],
        )
        assert "б/у техники" not in prompt

    def test_no_strict_order(self):
        prompt = build_seller_system_prompt(
            known_data={},
            missing_fields=["condition", "city", "specs"],
        )
        assert "СТРОГО по порядку" not in prompt

    def test_personality_present(self):
        prompt = build_seller_system_prompt(known_data={}, missing_fields=["condition"])
        assert "обычный человек" in prompt

    def test_conversation_summary_included(self):
        summary = "1. Ты: привет → Собеседник: да"
        prompt = build_seller_system_prompt(
            known_data={}, missing_fields=["condition"],
            conversation_summary=summary,
        )
        assert "КРАТКОЕ СОДЕРЖАНИЕ" in prompt
        assert summary in prompt

    def test_examples_present(self):
        prompt = build_seller_system_prompt(known_data={}, missing_fields=["condition"])
        assert "ты бот?" in prompt.lower()

    def test_respond_to_questions_instruction(self):
        prompt = build_seller_system_prompt(known_data={}, missing_fields=[])
        assert "СНАЧАЛА ответь" in prompt or "ответь на него" in prompt


# =====================================================
# Tests: build_buyer_system_prompt
# =====================================================

class TestBuildBuyerSystemPrompt:
    def test_known_preferences_not_asked(self):
        prompt = build_buyer_system_prompt(
            known_data={"preferences": "чёрный, 128гб"},
            missing_fields=["city", "price"],
        )
        assert "чёрный, 128гб" in prompt
        assert "предпочтения" not in prompt.lower().split("известно")[0]

    def test_never_reveal_price(self):
        prompt = build_buyer_system_prompt(
            known_data={},
            missing_fields=["preferences"],
        )
        assert "НИКОГДА не называй конкретную цену" in prompt

    def test_no_strict_order(self):
        prompt = build_buyer_system_prompt(
            known_data={},
            missing_fields=["preferences", "city", "price"],
        )
        assert "СТРОГО по порядку" not in prompt

    def test_buyer_examples_present(self):
        prompt = build_buyer_system_prompt(known_data={}, missing_fields=["price"])
        assert "130.000" in prompt or "130к" in prompt.lower()

    def test_conversation_summary_included(self):
        summary = "1. Ты: привет → Собеседник: да"
        prompt = build_buyer_system_prompt(
            known_data={}, missing_fields=["price"],
            conversation_summary=summary,
        )
        assert "КРАТКОЕ СОДЕРЖАНИЕ" in prompt
        assert summary in prompt


# =====================================================
# Tests: _products_match
# =====================================================

class TestProductsMatch:
    def test_same_product(self):
        assert _products_match("iPhone 15 Pro", "iPhone 15 Pro Max") is True

    def test_different_products(self):
        assert _products_match("цемент М500", "песок М500") is False

    def test_same_brand_different_model(self):
        assert _products_match("iPhone 14", "iPhone 15") is True

    def test_same_keyword_long(self):
        assert _products_match("MacBook Air M2", "MacBook Pro M2") is True

    def test_completely_different(self):
        assert _products_match("iPhone 15", "бетон М300") is False

    def test_empty_strings(self):
        assert _products_match("", "iPhone") is False
        assert _products_match("iPhone", "") is False
        assert _products_match("", "") is False

    def test_cyrillic_products(self):
        assert _products_match("кирпич красный", "кирпич белый") is True

    def test_same_construction_material(self):
        assert _products_match("арматура 12мм", "арматура 16мм") is True


# =====================================================
# Tests: _extract_preferences_from_text
# =====================================================

class TestExtractPreferences:
    def test_color_preference(self):
        result = _extract_preferences_from_text("хочу чёрный, 128гб")
        assert result is not None
        assert "чёрный" in result

    def test_no_preference(self):
        result = _extract_preferences_from_text("да, интересно")
        assert result is None

    def test_size_preference(self):
        result = _extract_preferences_from_text("нужен размер 42")
        assert result is not None

    def test_model_preference(self):
        result = _extract_preferences_from_text("интересует модель Pro Max")
        assert result is not None


# =====================================================
# Tests: detect_missing_fields with preferences
# =====================================================

class TestDetectMissingFieldsBuyer:
    def test_missing_preferences(self):
        deal = _make_deal()
        result = detect_missing_fields(deal, "buyer")
        assert "preferences" in result["missing"]

    def test_preferences_filled(self):
        deal = _make_deal(buyer_preferences="чёрный, 128гб")
        result = detect_missing_fields(deal, "buyer")
        assert "preferences" not in result["missing"]

    def test_preferences_discussed_in_context(self):
        deal = _make_deal()
        context = [
            {"role": "ai", "content": "какие предпочтения?"},
            {"role": "buyer", "content": "чёрный, 128 гб"},
        ]
        result = detect_missing_fields(deal, "buyer", context=context)
        # specs discussed → preferences not re-asked
        assert "preferences" not in result["missing"]

    def test_phone_block_includes_preferences(self):
        deal = _make_deal()
        result = detect_missing_fields(deal, "buyer")
        assert "предпочтения" in result["prompt_hint"]


# =====================================================
# Tests: _analyze_discussed_topics (expanded markers)
# =====================================================

class TestAnalyzeDiscussedTopics:
    def test_condition_quality(self):
        context = [{"role": "seller", "content": "качество отличное, без повреждений"}]
        discussed = _analyze_discussed_topics(context)
        assert "condition" in discussed

    def test_city_region(self):
        context = [{"role": "ai", "content": "а в каком регионе находишься?"}]
        discussed = _analyze_discussed_topics(context)
        assert "city" in discussed

    def test_specs_model(self):
        context = [{"role": "seller", "content": "модель 2024 года, размер XL"}]
        discussed = _analyze_discussed_topics(context)
        assert "specs" in discussed


# =====================================================
# Tests: build_conversation_summary
# =====================================================

class TestBuildConversationSummary:
    def test_empty_context(self):
        assert build_conversation_summary([]) == ""

    def test_single_message(self):
        assert build_conversation_summary([{"role": "ai", "content": "привет"}]) == ""

    def test_paired_exchange(self):
        ctx = [
            {"role": "ai", "content": "привет, товар актуален?"},
            {"role": "seller", "content": "да, продаю"},
        ]
        result = build_conversation_summary(ctx)
        assert "Ты:" in result
        assert "Собеседник:" in result

    def test_unanswered_question_flagged(self):
        ctx = [
            {"role": "ai", "content": "привет, товар актуален?"},
            {"role": "seller", "content": "да"},
            {"role": "ai", "content": "состояние какое?"},
            {"role": "seller", "content": "ты бот?"},
        ]
        result = build_conversation_summary(ctx)
        assert "НЕ ОТВЕЧЕНО" in result

    def test_normal_conversation_no_flags(self):
        ctx = [
            {"role": "ai", "content": "привет, товар актуален?"},
            {"role": "seller", "content": "да, продаю"},
            {"role": "ai", "content": "состояние какое?"},
            {"role": "seller", "content": "идеальное"},
        ]
        result = build_conversation_summary(ctx)
        assert "НЕ ОТВЕЧЕНО" not in result

    def test_multiple_exchanges(self):
        ctx = [
            {"role": "ai", "content": "привет"},
            {"role": "seller", "content": "привет"},
            {"role": "ai", "content": "состояние?"},
            {"role": "seller", "content": "идеал"},
            {"role": "ai", "content": "город?"},
            {"role": "seller", "content": "москва"},
        ]
        result = build_conversation_summary(ctx)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "1." in lines[0]
        assert "2." in lines[1]
        assert "3." in lines[2]


# =====================================================
# Tests: _detect_unanswered_question
# =====================================================

class TestDetectUnansweredQuestion:
    def test_question_mark(self):
        ctx = [{"role": "seller", "content": "ты бот?"}]
        assert _detect_unanswered_question(ctx) is not None

    def test_question_keyword(self):
        ctx = [{"role": "seller", "content": "ты бот что ли"}]
        result = _detect_unanswered_question(ctx)
        assert result is not None

    def test_no_question(self):
        ctx = [{"role": "seller", "content": "да, продаю"}]
        assert _detect_unanswered_question(ctx) is None

    def test_ai_last_message(self):
        ctx = [{"role": "ai", "content": "как дела?"}]
        assert _detect_unanswered_question(ctx) is None

    def test_empty_context(self):
        assert _detect_unanswered_question([]) is None

    def test_why_question(self):
        ctx = [{"role": "buyer", "content": "а почему так дорого"}]
        result = _detect_unanswered_question(ctx)
        assert result is not None


# =====================================================
# Tests: extract_price with dot-separator
# =====================================================

class TestExtractPriceDotSeparator:
    def test_130_000(self):
        assert extract_price("бюджет 130.000") == Decimal("130000")

    def test_1_500_000(self):
        assert extract_price("цена 1.500.000") == Decimal("1500000")

    def test_50_000(self):
        assert extract_price("отдам за 50.000") == Decimal("50000")

    def test_regular_130k(self):
        assert extract_price("130к") == Decimal("130000")

    def test_regular_50000(self):
        assert extract_price("цена 50000") == Decimal("50000")

    def test_small_decimal_not_price(self):
        # "3.5" should not be a valid price (too small)
        assert extract_price("3.5 кг") is None
