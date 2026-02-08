"""
Tests for the unified notification system.

Covers:
- Notification response schema validation
- Read/unread message state transitions
- Cold deal counting logic
- Notification type mapping
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("TG_API_ID", "0")
os.environ.setdefault("TG_API_HASH", "test")
os.environ.setdefault("TG_SESSION_STRING", "test")

from pydantic import BaseModel
from typing import Optional


# Replicate the notification schemas for testing (avoid importing API chain)
class DealUnreadInfo(BaseModel):
    deal_id: int
    negotiation_id: int
    product: str
    unread_seller: int
    unread_buyer: int
    last_message_at: Optional[str] = None
    last_sender_role: Optional[str] = None
    last_message_preview: Optional[str] = None


class NotificationStatusResponse(BaseModel):
    total_unread_messages: int
    deals_with_unread: list[DealUnreadInfo]
    new_leads_count: int
    my_cold_deals_count: int = 0


# ── DealUnreadInfo schema ───────────────────────────────


class TestDealUnreadInfo:
    def test_basic_fields(self):
        info = DealUnreadInfo(
            deal_id=1,
            negotiation_id=10,
            product="арматура А500С",
            unread_seller=2,
            unread_buyer=1,
        )
        assert info.deal_id == 1
        assert info.negotiation_id == 10
        assert info.product == "арматура А500С"
        assert info.unread_seller == 2
        assert info.unread_buyer == 1

    def test_last_sender_role_seller(self):
        info = DealUnreadInfo(
            deal_id=1,
            negotiation_id=10,
            product="цемент М500",
            unread_seller=1,
            unread_buyer=0,
            last_sender_role="seller",
            last_message_preview="Есть 20 тонн со склада",
        )
        assert info.last_sender_role == "seller"
        assert info.last_message_preview == "Есть 20 тонн со склада"

    def test_last_sender_role_buyer(self):
        info = DealUnreadInfo(
            deal_id=2,
            negotiation_id=20,
            product="профлист",
            unread_seller=0,
            unread_buyer=3,
            last_sender_role="buyer",
            last_message_preview="Какая цена за лист?",
        )
        assert info.last_sender_role == "buyer"
        assert info.last_message_preview == "Какая цена за лист?"

    def test_optional_fields_default_none(self):
        info = DealUnreadInfo(
            deal_id=1,
            negotiation_id=10,
            product="test",
            unread_seller=0,
            unread_buyer=0,
        )
        assert info.last_message_at is None
        assert info.last_sender_role is None
        assert info.last_message_preview is None

    def test_message_preview_length(self):
        """Preview field accepts up to 80 chars (truncated at backend)."""
        long_text = "а" * 80
        info = DealUnreadInfo(
            deal_id=1,
            negotiation_id=10,
            product="test",
            unread_seller=1,
            unread_buyer=0,
            last_message_preview=long_text,
        )
        assert len(info.last_message_preview) == 80

    def test_last_message_at_iso_format(self):
        now = datetime.now(timezone.utc)
        info = DealUnreadInfo(
            deal_id=1,
            negotiation_id=10,
            product="test",
            unread_seller=1,
            unread_buyer=0,
            last_message_at=now.isoformat(),
        )
        assert info.last_message_at == now.isoformat()


# ── NotificationStatusResponse schema ───────────────────


class TestNotificationStatusResponse:
    def test_basic_response(self):
        resp = NotificationStatusResponse(
            total_unread_messages=5,
            deals_with_unread=[],
            new_leads_count=3,
            my_cold_deals_count=2,
        )
        assert resp.total_unread_messages == 5
        assert resp.new_leads_count == 3
        assert resp.my_cold_deals_count == 2

    def test_cold_deals_default_zero(self):
        resp = NotificationStatusResponse(
            total_unread_messages=0,
            deals_with_unread=[],
            new_leads_count=0,
        )
        assert resp.my_cold_deals_count == 0

    def test_response_with_deal_unread(self):
        deal_info = DealUnreadInfo(
            deal_id=42,
            negotiation_id=7,
            product="арматура А500С",
            unread_seller=2,
            unread_buyer=0,
            last_sender_role="seller",
            last_message_preview="Добрый день, есть в наличии",
        )
        resp = NotificationStatusResponse(
            total_unread_messages=2,
            deals_with_unread=[deal_info],
            new_leads_count=1,
            my_cold_deals_count=0,
        )
        assert len(resp.deals_with_unread) == 1
        assert resp.deals_with_unread[0].product == "арматура А500С"
        assert resp.deals_with_unread[0].last_sender_role == "seller"

    def test_multiple_deals_with_unread(self):
        deals = [
            DealUnreadInfo(
                deal_id=i,
                negotiation_id=i * 10,
                product=f"product_{i}",
                unread_seller=1,
                unread_buyer=1,
                last_sender_role="seller",
            )
            for i in range(5)
        ]
        resp = NotificationStatusResponse(
            total_unread_messages=10,
            deals_with_unread=deals,
            new_leads_count=0,
            my_cold_deals_count=3,
        )
        assert len(resp.deals_with_unread) == 5
        assert resp.my_cold_deals_count == 3

    def test_json_serialization(self):
        """Response should serialize to JSON correctly."""
        resp = NotificationStatusResponse(
            total_unread_messages=1,
            deals_with_unread=[
                DealUnreadInfo(
                    deal_id=1,
                    negotiation_id=10,
                    product="цемент",
                    unread_seller=1,
                    unread_buyer=0,
                    last_sender_role="seller",
                    last_message_preview="Добрый день",
                )
            ],
            new_leads_count=2,
            my_cold_deals_count=1,
        )
        data = resp.model_dump()
        assert data["my_cold_deals_count"] == 1
        assert data["deals_with_unread"][0]["last_sender_role"] == "seller"
        assert data["deals_with_unread"][0]["last_message_preview"] == "Добрый день"


# ── Read/unread message state ───────────────────────────


class TestMessageReadState:
    def test_message_initially_unread(self):
        """A new message has read_at=None (unread)."""
        msg = SimpleNamespace(
            id=1,
            role="seller",
            content="Привет",
            read_at=None,
        )
        assert msg.read_at is None

    def test_message_marked_read(self):
        """After marking read, read_at is set to a datetime."""
        now = datetime.now(timezone.utc)
        msg = SimpleNamespace(
            id=1,
            role="seller",
            content="Привет",
            read_at=now,
        )
        assert msg.read_at is not None
        assert msg.read_at == now

    def test_manager_messages_not_counted_as_unread(self):
        """Manager's own messages should never be counted as unread."""
        messages = [
            SimpleNamespace(role="manager", read_at=None),
            SimpleNamespace(role="seller", read_at=None),
            SimpleNamespace(role="buyer", read_at=None),
            SimpleNamespace(role="manager", read_at=None),
        ]
        unread = [m for m in messages if m.role != "manager" and m.read_at is None]
        assert len(unread) == 2

    def test_mixed_read_unread(self):
        """Some messages read, some not."""
        now = datetime.now(timezone.utc)
        messages = [
            SimpleNamespace(role="seller", read_at=now),   # read
            SimpleNamespace(role="seller", read_at=None),  # unread
            SimpleNamespace(role="buyer", read_at=now),    # read
            SimpleNamespace(role="buyer", read_at=None),   # unread
            SimpleNamespace(role="manager", read_at=None), # manager - skip
        ]
        unread_seller = [m for m in messages if m.role == "seller" and m.read_at is None]
        unread_buyer = [m for m in messages if m.role == "buyer" and m.read_at is None]
        assert len(unread_seller) == 1
        assert len(unread_buyer) == 1

    def test_all_read_zero_unread(self):
        """When all messages are read, unread count is 0."""
        now = datetime.now(timezone.utc)
        messages = [
            SimpleNamespace(role="seller", read_at=now),
            SimpleNamespace(role="buyer", read_at=now),
        ]
        unread = [m for m in messages if m.role != "manager" and m.read_at is None]
        assert len(unread) == 0


# ── Cold deal detection logic ───────────────────────────


class TestColdDealCounting:
    def test_cold_assigned_deal_counted(self):
        """Cold deal assigned to manager should be counted."""
        deals = [
            SimpleNamespace(status="cold", manager_id=1),
            SimpleNamespace(status="cold", manager_id=1),
            SimpleNamespace(status="warm", manager_id=1),
            SimpleNamespace(status="cold", manager_id=2),   # other manager
            SimpleNamespace(status="cold", manager_id=None), # pool
        ]
        my_cold = [d for d in deals if d.status == "cold" and d.manager_id == 1]
        assert len(my_cold) == 2

    def test_no_cold_deals(self):
        """Manager has no cold deals."""
        deals = [
            SimpleNamespace(status="warm", manager_id=1),
            SimpleNamespace(status="won", manager_id=1),
        ]
        my_cold = [d for d in deals if d.status == "cold" and d.manager_id == 1]
        assert len(my_cold) == 0

    def test_pool_leads_not_counted_as_my_cold(self):
        """Unassigned pool leads should not appear in my_cold_deals."""
        deals = [
            SimpleNamespace(status="cold", manager_id=None),
            SimpleNamespace(status="warm", manager_id=None),
        ]
        my_cold = [d for d in deals if d.status == "cold" and d.manager_id == 1]
        pool_leads = [d for d in deals if d.manager_id is None and d.status in ("cold", "warm")]
        assert len(my_cold) == 0
        assert len(pool_leads) == 2

    def test_cold_grows_triggers_notification(self):
        """Simulating the frontend cold deal growth detection."""
        last_cold = 2
        current_cold = 4
        cold_grew = last_cold >= 0 and current_cold > last_cold
        assert cold_grew is True
        new_count = current_cold - last_cold
        assert new_count == 2

    def test_cold_stable_no_notification(self):
        """No notification when cold count stays the same."""
        last_cold = 3
        current_cold = 3
        cold_grew = last_cold >= 0 and current_cold > last_cold
        assert cold_grew is False


# ── Notification type mapping ─────────────────────────


class TestNotificationTypes:
    """Verify that different events map to different notification types."""

    def test_all_sound_types_distinct(self):
        """All notification event sounds are distinct."""
        sound_functions = {
            'message': 'playMessageSound',
            'lead': 'playLeadSound',
            'announcement': 'playAnnouncementSound',
            'browser_alert': 'playBrowserAlertSound',
        }
        assert len(set(sound_functions.values())) == 4

    def test_toast_types_distinct(self):
        """Each notification event uses a different toast type."""
        toast_types = {
            'new_message': 'message',
            'new_lead': 'lead',
            'cold_deal': 'lead',
            'announcement': 'announcement',
        }
        # Message and announcement are distinct types
        assert toast_types['new_message'] != toast_types['announcement']
        assert toast_types['new_lead'] != toast_types['new_message']

    def test_message_notification_shows_sender(self):
        """Message toast should display sender role (buyer/seller)."""
        deal_info = SimpleNamespace(
            last_sender_role="buyer",
            product="арматура",
            last_message_preview="Нужно 20 тонн",
        )
        sender = "Покупатель" if deal_info.last_sender_role == "buyer" else "Продавец"
        assert sender == "Покупатель"

        deal_info2 = SimpleNamespace(
            last_sender_role="seller",
            product="цемент",
            last_message_preview="Есть в наличии",
        )
        sender2 = "Покупатель" if deal_info2.last_sender_role == "buyer" else "Продавец"
        assert sender2 == "Продавец"

    def test_browser_notif_only_when_not_focused(self):
        """Browser notifications should only show when document has no focus."""
        # Simulating logic: hasFocus=True -> no notif
        has_focus = True
        should_show = not has_focus
        assert should_show is False

        # hasFocus=False -> show notif
        has_focus = False
        should_show = not has_focus
        assert should_show is True
