"""
Seed test data for Arbion CRM testing.

Usage:
    python scripts/seed_test_data.py

Or with custom DATABASE_URL:
    DATABASE_URL="postgresql://..." python scripts/seed_test_data.py

This script creates:
- Test orders (buy/sell)
- Test deals in various statuses (COLD, IN_PROGRESS, WARM)
- Test negotiations with messages
- Test manager user (if not exists)
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.models import (
    User, UserRole, Order, OrderType, DetectedDeal, DealStatus,
    Negotiation, NegotiationStage, NegotiationMessage, MonitoredChat, ChatStatus, ChatSource
)
from src.utils.password import get_password_hash


# Railway PostgreSQL URL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:eehVvqlgriwncHLOlughMeacVrySHtTj@caboose.proxy.rlwy.net:46468/railway"
)

# Convert to asyncpg format if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# ===== TEST DATA =====

# Telegram IDs for testing (replace with your actual IDs)
# YOUR_MAIN_ACCOUNT_ID = 123456789  # Your personal Telegram ID
# YOUR_BOT_ACCOUNT_ID = 987654321   # Bot's Telegram ID

TEST_PRODUCTS = [
    {"name": "iPhone 15 Pro Max", "buy_price": 95000, "sell_price": 105000},
    {"name": "MacBook Pro M3", "buy_price": 180000, "sell_price": 200000},
    {"name": "Samsung Galaxy S24 Ultra", "buy_price": 85000, "sell_price": 95000},
    {"name": "PlayStation 5", "buy_price": 45000, "sell_price": 55000},
    {"name": "Apple Watch Ultra 2", "buy_price": 65000, "sell_price": 75000},
]

TEST_REGIONS = ["Москва", "СПб", "Казань", "Новосибирск", "Екатеринбург"]


async def create_test_manager(db: AsyncSession) -> User:
    """Create a test manager user."""
    # Check if test manager exists
    result = await db.execute(
        select(User).where(User.username == "test_manager")
    )
    manager = result.scalar_one_or_none()

    if not manager:
        manager = User(
            username="test_manager",
            password_hash=get_password_hash("test123"),
            role=UserRole.MANAGER,
            display_name="Тест Менеджер",
            is_active=True,
        )
        db.add(manager)
        await db.commit()
        await db.refresh(manager)
        print(f"Created test manager: test_manager / test123")
    else:
        print(f"Test manager already exists (id={manager.id})")

    return manager


async def create_test_chat(db: AsyncSession, chat_id: int, title: str) -> MonitoredChat:
    """Create a monitored chat for testing."""
    result = await db.execute(
        select(MonitoredChat).where(MonitoredChat.chat_id == chat_id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        chat = MonitoredChat(
            chat_id=chat_id,
            title=title,
            member_count=1000,
            status=ChatStatus.ACTIVE,
            source=ChatSource.SEED,
            useful_ratio=0.75,
            orders_found=50,
            deals_created=10,
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        print(f"Created test chat: {title}")

    return chat


async def create_test_orders(
    db: AsyncSession,
    chat_id: int,
    buyer_id: int,
    seller_id: int,
) -> tuple[Order, Order]:
    """Create buy and sell orders for testing."""
    product = TEST_PRODUCTS[0]
    region = TEST_REGIONS[0]

    # Buy order
    buy_order = Order(
        order_type=OrderType.BUY,
        chat_id=chat_id,
        sender_id=buyer_id,
        message_id=1001,
        product=product["name"],
        price=Decimal(str(product["buy_price"])),
        quantity="1 шт",
        region=region,
        raw_text=f"Куплю {product['name']} за {product['buy_price']}р, {region}",
        contact_info="@buyer_test",
        is_active=True,
    )

    # Sell order
    sell_order = Order(
        order_type=OrderType.SELL,
        chat_id=chat_id,
        sender_id=seller_id,
        message_id=1002,
        product=product["name"],
        price=Decimal(str(product["sell_price"])),
        quantity="1 шт",
        region=region,
        raw_text=f"Продам {product['name']} за {product['sell_price']}р, {region}, новый в упаковке",
        contact_info="@seller_test",
        is_active=True,
    )

    db.add(buy_order)
    db.add(sell_order)
    await db.commit()
    await db.refresh(buy_order)
    await db.refresh(sell_order)

    print(f"Created orders: buy #{buy_order.id}, sell #{sell_order.id}")
    return buy_order, sell_order


async def create_test_deal(
    db: AsyncSession,
    buy_order: Order,
    sell_order: Order,
    status: DealStatus,
    manager: User | None = None,
) -> DetectedDeal:
    """Create a detected deal."""
    buy_price = float(buy_order.price or 0)
    sell_price = float(sell_order.price or 0)
    margin = buy_price - sell_price  # profit margin

    deal = DetectedDeal(
        buy_order_id=buy_order.id,
        sell_order_id=sell_order.id,
        product=buy_order.product,
        region=buy_order.region,
        buy_price=buy_order.price,
        sell_price=sell_order.price,
        margin=Decimal(str(abs(margin))),
        status=status,
        buyer_chat_id=buy_order.chat_id,
        buyer_sender_id=buy_order.sender_id,
    )

    if manager and status in [DealStatus.HANDED_TO_MANAGER, DealStatus.WARM]:
        deal.manager_id = manager.id
        deal.assigned_at = datetime.now(timezone.utc)

    if status == DealStatus.IN_PROGRESS:
        deal.ai_insight = "AI начал переговоры. Продавец ответил положительно."
    elif status == DealStatus.WARM:
        deal.ai_insight = "Продавец заинтересован, готов к сделке. Рекомендую связаться."

    db.add(deal)
    await db.commit()
    await db.refresh(deal)

    print(f"Created deal #{deal.id} ({status.value})")
    return deal


async def create_test_negotiation(
    db: AsyncSession,
    deal: DetectedDeal,
    seller_id: int,
    stage: NegotiationStage,
) -> Negotiation:
    """Create a negotiation with test messages."""
    negotiation = Negotiation(
        deal_id=deal.id,
        seller_chat_id=deal.sell_order.chat_id,
        seller_sender_id=seller_id,
        stage=stage,
    )
    db.add(negotiation)
    await db.commit()
    await db.refresh(negotiation)

    # Add test messages based on stage
    messages = []

    if stage in [NegotiationStage.INITIAL, NegotiationStage.PRICE_DISCUSSION, NegotiationStage.WARM]:
        messages.append(NegotiationMessage(
            negotiation_id=negotiation.id,
            role="ai",
            content=f"Здравствуйте! Заинтересовал ваш {deal.product}. Актуально?",
        ))

    if stage in [NegotiationStage.PRICE_DISCUSSION, NegotiationStage.WARM]:
        messages.append(NegotiationMessage(
            negotiation_id=negotiation.id,
            role="seller",
            content="Да, актуально! В наличии, новый в упаковке.",
        ))
        messages.append(NegotiationMessage(
            negotiation_id=negotiation.id,
            role="ai",
            content="Отлично! По цене возможен торг? Готов забрать сегодня.",
        ))

    if stage == NegotiationStage.WARM:
        messages.append(NegotiationMessage(
            negotiation_id=negotiation.id,
            role="seller",
            content="Да, при самовывозе скину 3000р. Могу скинуть фото/видео.",
        ))
        messages.append(NegotiationMessage(
            negotiation_id=negotiation.id,
            role="ai",
            content="Отлично, готов встретиться. Где удобно?",
        ))

    for msg in messages:
        db.add(msg)

    await db.commit()
    print(f"Created negotiation #{negotiation.id} ({stage.value}) with {len(messages)} messages")
    return negotiation


async def seed_all(
    main_account_id: int = 123456789,
    bot_account_id: int = 987654321,
    test_chat_id: int = -1001234567890,
):
    """Seed all test data."""
    print(f"\nConnecting to database...")
    print(f"URL: {DATABASE_URL[:50]}...")

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        print("\n=== Creating test data ===\n")

        # 1. Create test manager
        manager = await create_test_manager(db)

        # 2. Create test monitored chat
        chat = await create_test_chat(db, test_chat_id, "Test Trade Group")

        # 3. Create COLD deal (no negotiation yet)
        print("\n--- COLD deal ---")
        buy1, sell1 = await create_test_orders(db, test_chat_id, main_account_id, bot_account_id)
        deal_cold = await create_test_deal(db, buy1, sell1, DealStatus.COLD)

        # 4. Create IN_PROGRESS deal (AI negotiating)
        print("\n--- IN_PROGRESS deal ---")
        buy2, sell2 = await create_test_orders(db, test_chat_id, main_account_id, bot_account_id)
        deal_progress = await create_test_deal(db, buy2, sell2, DealStatus.IN_PROGRESS)
        await create_test_negotiation(db, deal_progress, bot_account_id, NegotiationStage.PRICE_DISCUSSION)

        # 5. Create WARM deal (ready for manager)
        print("\n--- WARM deal ---")
        buy3, sell3 = await create_test_orders(db, test_chat_id, main_account_id, bot_account_id)
        deal_warm = await create_test_deal(db, buy3, sell3, DealStatus.WARM, manager)
        await create_test_negotiation(db, deal_warm, bot_account_id, NegotiationStage.WARM)

        print("\n" + "="*50)
        print("TEST DATA CREATED SUCCESSFULLY!")
        print("="*50)
        print(f"""
Deals created:
  - COLD deal #{deal_cold.id} - waiting for AI contact
  - IN_PROGRESS deal #{deal_progress.id} - AI negotiating
  - WARM deal #{deal_warm.id} - ready for manager

Test login:
  - Manager: test_manager / test123

Telegram IDs used:
  - Buyer (main account): {main_account_id}
  - Seller (bot account): {bot_account_id}
  - Test chat: {test_chat_id}

To test chatting:
  1. Replace the IDs in this script with your actual Telegram IDs
  2. Re-run the script
  3. The bot will try to contact seller_id when processing COLD deals
        """)

    await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed test data for Arbion")
    parser.add_argument("--main-id", type=int, default=123456789, help="Your main Telegram account ID")
    parser.add_argument("--bot-id", type=int, default=987654321, help="Bot's Telegram account ID")
    parser.add_argument("--chat-id", type=int, default=-1001234567890, help="Test chat ID")

    args = parser.parse_args()

    asyncio.run(seed_all(
        main_account_id=args.main_id,
        bot_account_id=args.bot_id,
        test_chat_id=args.chat_id,
    ))
