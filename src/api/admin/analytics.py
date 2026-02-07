"""Admin analytics API endpoints.

New endpoints for Section 7:
- GET /analytics/niches    — Analytics by niche
- GET /analytics/managers  — Extended manager analytics
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import (
    DealStatus,
    DetectedDeal,
    LedgerEntry,
    User,
    UserRole,
)

router = APIRouter(prefix="/analytics")


@router.get("/niches")
async def niche_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """
    Analytics grouped by niche.

    Returns: {
        "стройматериалы": { "deals": 15, "revenue": 450000, "avg_margin": 30000 },
        ...
    }
    """
    # Count deals by niche
    deals_query = (
        select(
            DetectedDeal.niche,
            func.count(DetectedDeal.id).label("deals"),
            func.count(
                case(
                    (DetectedDeal.status == DealStatus.WON, DetectedDeal.id),
                )
            ).label("won_deals"),
            func.coalesce(func.sum(DetectedDeal.profit), 0).label("revenue"),
            func.coalesce(func.avg(DetectedDeal.margin), 0).label("avg_margin"),
        )
        .group_by(DetectedDeal.niche)
    )

    result = await db.execute(deals_query)
    rows = result.fetchall()

    analytics = {}
    for row in rows:
        niche_key = row.niche or "unknown"
        analytics[niche_key] = {
            "deals": row.deals,
            "won_deals": row.won_deals,
            "revenue": float(row.revenue or 0),
            "avg_margin": round(float(row.avg_margin or 0), 2),
        }

    return analytics


@router.get("/managers")
async def manager_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """
    Extended manager analytics.

    Returns list of managers with:
    - system_deals, manager_deals counts
    - commission_total
    - conversion_rate
    """
    # Get all managers
    managers_result = await db.execute(
        select(User).where(User.role == UserRole.MANAGER)
    )
    managers = managers_result.scalars().all()

    analytics = []
    for manager in managers:
        # Count deals by lead source
        system_deals = await db.scalar(
            select(func.count())
            .select_from(DetectedDeal)
            .where(
                DetectedDeal.manager_id == manager.id,
                DetectedDeal.lead_source == "system",
            )
        ) or 0

        manager_deals = await db.scalar(
            select(func.count())
            .select_from(DetectedDeal)
            .where(
                DetectedDeal.manager_id == manager.id,
                DetectedDeal.lead_source == "manager",
            )
        ) or 0

        total_deals = system_deals + manager_deals

        # Won deals count
        won_deals = await db.scalar(
            select(func.count())
            .select_from(DetectedDeal)
            .where(
                DetectedDeal.manager_id == manager.id,
                DetectedDeal.status == DealStatus.WON,
            )
        ) or 0

        # Total commission from ledger
        commission_total = await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.manager_commission), 0))
            .where(LedgerEntry.closed_by_user_id == manager.id)
        ) or Decimal("0")

        # Conversion rate
        eligible_deals = await db.scalar(
            select(func.count())
            .select_from(DetectedDeal)
            .where(
                DetectedDeal.manager_id == manager.id,
                DetectedDeal.status.in_([DealStatus.WON, DealStatus.LOST]),
            )
        ) or 0

        conversion_rate = (
            round(won_deals / eligible_deals * 100, 1)
            if eligible_deals > 0
            else 0.0
        )

        analytics.append({
            "manager_id": manager.id,
            "display_name": manager.display_name,
            "is_active": manager.is_active,
            "level": manager.level,
            "system_deals": system_deals,
            "manager_deals": manager_deals,
            "total_deals": total_deals,
            "won_deals": won_deals,
            "commission_total": float(commission_total),
            "conversion_rate": conversion_rate,
        })

    return analytics
