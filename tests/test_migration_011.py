"""
Tests for migration 011_strategic_update.

Verifies that all new columns are present in models after create_all,
and that the migration script itself is structurally correct.
"""

import os
import sys

# Set required env var before importing src modules
os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

import pytest
import pytest_asyncio
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def inspector(engine):
    """Return a dict of {table_name: [column_names]}."""
    async with engine.connect() as conn:
        def _inspect(sync_conn):
            insp = sa_inspect(sync_conn)
            tables = {}
            for table in insp.get_table_names():
                tables[table] = [c["name"] for c in insp.get_columns(table)]
            return tables
        return await conn.run_sync(_inspect)


# ── orders table ────────────────────────────────────────────

class TestOrdersNewColumns:
    """All new columns from СЕКЦИЯ 1 exist in 'orders' table."""

    def test_platform_column(self, inspector):
        assert "platform" in inspector["orders"]

    def test_niche_column(self, inspector):
        assert "niche" in inspector["orders"]

    def test_unit_column(self, inspector):
        assert "unit" in inspector["orders"]

    def test_volume_numeric_column(self, inspector):
        assert "volume_numeric" in inspector["orders"]


# ── detected_deals table ───────────────────────────────────

class TestDetectedDealsNewColumns:
    """All new columns from СЕКЦИЯ 1 exist in 'detected_deals' table."""

    def test_lead_source_column(self, inspector):
        assert "lead_source" in inspector["detected_deals"]

    def test_niche_column(self, inspector):
        assert "niche" in inspector["detected_deals"]

    def test_deal_model_column(self, inspector):
        assert "deal_model" in inspector["detected_deals"]

    def test_manager_commission_rate_column(self, inspector):
        assert "manager_commission_rate" in inspector["detected_deals"]

    def test_buyer_payment_status_column(self, inspector):
        assert "buyer_payment_status" in inspector["detected_deals"]

    def test_seller_payment_status_column(self, inspector):
        assert "seller_payment_status" in inspector["detected_deals"]

    def test_our_commission_status_column(self, inspector):
        assert "our_commission_status" in inspector["detected_deals"]

    def test_payment_method_column(self, inspector):
        assert "payment_method" in inspector["detected_deals"]

    def test_ai_draft_message_column(self, inspector):
        assert "ai_draft_message" in inspector["detected_deals"]

    def test_market_price_context_column(self, inspector):
        assert "market_price_context" in inspector["detected_deals"]

    def test_platform_column(self, inspector):
        assert "platform" in inspector["detected_deals"]


# ── users table ─────────────────────────────────────────────

class TestUsersNewColumns:
    """All new columns from СЕКЦИЯ 1 exist in 'users' table."""

    def test_niches_column(self, inspector):
        assert "niches" in inspector["users"]

    def test_level_column(self, inspector):
        assert "level" in inspector["users"]

    def test_telegram_user_id_column(self, inspector):
        assert "telegram_user_id" in inspector["users"]


# ── ledger table ────────────────────────────────────────────

class TestLedgerNewColumns:
    """All new columns from СЕКЦИЯ 1 exist in 'ledger' table."""

    def test_deal_model_column(self, inspector):
        assert "deal_model" in inspector["ledger"]

    def test_commission_rate_applied_column(self, inspector):
        assert "commission_rate_applied" in inspector["ledger"]

    def test_lead_source_column(self, inspector):
        assert "lead_source" in inspector["ledger"]


# ── monitored_chats table ──────────────────────────────────

class TestMonitoredChatsNewColumns:
    """All new columns from СЕКЦИЯ 1 exist in 'monitored_chats' table."""

    def test_niche_column(self, inspector):
        assert "niche" in inspector["monitored_chats"]

    def test_platform_column(self, inspector):
        assert "platform" in inspector["monitored_chats"]


# ── Migration script structural checks ─────────────────────

class TestMigrationScript:
    """Validate migration script structure and metadata (source-level checks)."""

    @pytest.fixture
    def source(self):
        import pathlib
        fpath = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions" / "011_strategic_update.py"
        return fpath.read_text(encoding="utf-8")

    def test_revision_id(self, source):
        assert 'revision: str = "011_strategic_update"' in source

    def test_down_revision(self, source):
        assert 'down_revision' in source
        assert '"010_telegram_message_id"' in source

    def test_has_upgrade_function(self, source):
        assert "def upgrade()" in source

    def test_has_downgrade_function(self, source):
        assert "def downgrade()" in source

    def test_upgrade_covers_all_tables(self, source):
        """Upgrade section mentions all 5 tables."""
        # Extract text between "def upgrade" and "def downgrade"
        up_start = source.index("def upgrade()")
        down_start = source.index("def downgrade()")
        upgrade_body = source[up_start:down_start]
        for table in ["orders", "detected_deals", "users", "ledger", "monitored_chats"]:
            assert table in upgrade_body, f"Table '{table}' not found in upgrade()"

    def test_downgrade_covers_all_tables(self, source):
        """Downgrade section mentions all 5 tables."""
        down_start = source.index("def downgrade()")
        downgrade_body = source[down_start:]
        for table in ["orders", "detected_deals", "users", "ledger", "monitored_chats"]:
            assert table in downgrade_body, f"Table '{table}' not found in downgrade()"

    def test_all_columns_in_upgrade(self, source):
        """Every new column name appears in upgrade()."""
        up_start = source.index("def upgrade()")
        down_start = source.index("def downgrade()")
        upgrade_body = source[up_start:down_start]
        expected_columns = [
            "platform", "niche", "unit", "volume_numeric",
            "lead_source", "deal_model", "manager_commission_rate",
            "buyer_payment_status", "seller_payment_status",
            "our_commission_status", "payment_method",
            "ai_draft_message", "market_price_context",
            "niches", "level", "telegram_user_id",
            "commission_rate_applied",
        ]
        for col in expected_columns:
            assert col in upgrade_body, f"Column '{col}' not found in upgrade()"

    def test_all_columns_in_downgrade(self, source):
        """Every new column name appears in downgrade()."""
        down_start = source.index("def downgrade()")
        downgrade_body = source[down_start:]
        expected_columns = [
            "platform", "niche", "unit", "volume_numeric",
            "lead_source", "deal_model", "manager_commission_rate",
            "buyer_payment_status", "seller_payment_status",
            "our_commission_status", "payment_method",
            "ai_draft_message", "market_price_context",
            "niches", "level", "telegram_user_id",
            "commission_rate_applied",
        ]
        for col in expected_columns:
            assert col in downgrade_body, f"Column '{col}' not found in downgrade()"

    def test_idempotency_guards(self, source):
        """Every add_column is guarded by _col_exists check."""
        import re
        add_count = len(re.findall(r'op\.add_column', source))
        guard_count = len(re.findall(r'if not _col_exists', source))
        assert guard_count == add_count, (
            f"Mismatch: {add_count} add_column vs {guard_count} _col_exists guards"
        )

    def test_downgrade_idempotency_guards(self, source):
        """Every drop_column is guarded by _col_exists check."""
        import re
        down_start = source.index("def downgrade()")
        downgrade_body = source[down_start:]
        drop_count = len(re.findall(r'op\.drop_column', downgrade_body))
        guard_count = len(re.findall(r'if _col_exists\(', downgrade_body))
        assert guard_count == drop_count, (
            f"Mismatch: {drop_count} drop_column vs {guard_count} _col_exists guards in downgrade"
        )


# ── Model defaults test ────────────────────────────────────

class TestModelDefaults:
    """Test that ORM models have correct defaults for new fields."""

    def test_order_platform_default(self):
        from src.models.order import Order
        col = Order.__table__.columns["platform"]
        assert col.default is not None or col.server_default is not None

    def test_deal_lead_source_default(self):
        from src.models.deal import DetectedDeal
        col = DetectedDeal.__table__.columns["lead_source"]
        assert col.default is not None or col.server_default is not None

    def test_deal_deal_model_default(self):
        from src.models.deal import DetectedDeal
        col = DetectedDeal.__table__.columns["deal_model"]
        assert col.default is not None or col.server_default is not None

    def test_deal_payment_defaults(self):
        from src.models.deal import DetectedDeal
        for col_name in ["buyer_payment_status", "seller_payment_status", "our_commission_status"]:
            col = DetectedDeal.__table__.columns[col_name]
            assert col.default is not None or col.server_default is not None, (
                f"{col_name} has no default"
            )

    def test_user_level_default(self):
        from src.models.user import User
        col = User.__table__.columns["level"]
        assert col.default is not None or col.server_default is not None

    def test_chat_platform_default(self):
        from src.models.chat import MonitoredChat
        col = MonitoredChat.__table__.columns["platform"]
        assert col.default is not None or col.server_default is not None
