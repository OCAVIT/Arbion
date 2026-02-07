"""
Deal routing service for automatic manager assignment.

When a deal becomes 'warm' and auto-assignment is enabled,
this service assigns it to the manager with the lowest workload.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import DealStatus, DetectedDeal, SystemSetting, User, UserRole
from src.services.commission import calculate_commission_rate

logger = logging.getLogger(__name__)


async def get_setting(db: AsyncSession, key: str, default=None):
    """Get a system setting value."""
    setting = await db.get(SystemSetting, key)
    if setting:
        return setting.get_value()
    return default


async def assign_deal_to_manager(deal_id: int, db: AsyncSession) -> bool:
    """
    Automatically assign a warm deal to the least busy manager.

    This is called when:
    1. A deal's status changes to WARM
    2. Assignment mode is 'auto'

    Args:
        deal_id: ID of the deal to assign
        db: Database session

    Returns:
        True if deal was assigned, False otherwise
    """
    # Check assignment mode
    assignment_mode = await get_setting(db, "assignment_mode", "free_pool")
    if assignment_mode != "auto":
        logger.debug(f"Assignment mode is '{assignment_mode}', skipping auto-assignment")
        return False

    # Get the deal
    deal = await db.get(DetectedDeal, deal_id)
    if not deal:
        logger.warning(f"Deal {deal_id} not found")
        return False

    if deal.manager_id is not None:
        logger.debug(f"Deal {deal_id} already assigned to manager {deal.manager_id}")
        return False

    if deal.status != DealStatus.WARM:
        logger.debug(f"Deal {deal_id} is not warm (status: {deal.status})")
        return False

    # Get max deals per manager
    max_deals = await get_setting(db, "max_deals_per_manager", 15)

    # Find all active managers with their active deal counts
    result = await db.execute(
        select(User)
        .where(
            and_(
                User.role == UserRole.MANAGER,
                User.is_active == True,
            )
        )
        .options(selectinload(User.assigned_deals))
    )
    managers = result.scalars().all()

    if not managers:
        logger.warning("No active managers found for auto-assignment")
        return False

    # Calculate workload for each manager
    available_managers = []
    for manager in managers:
        active_count = sum(
            1 for d in manager.assigned_deals
            if d.status in [DealStatus.IN_PROGRESS, DealStatus.WARM, DealStatus.HANDED_TO_MANAGER]
        )

        if active_count < max_deals:
            available_managers.append((manager, active_count))

    if not available_managers:
        logger.warning(f"All managers at max capacity ({max_deals} deals)")
        return False

    # Select manager with lowest workload
    selected_manager = min(available_managers, key=lambda x: x[1])[0]

    # Assign deal
    deal.manager_id = selected_manager.id
    deal.assigned_at = datetime.now(timezone.utc)
    deal.status = DealStatus.HANDED_TO_MANAGER
    deal.manager_commission_rate = calculate_commission_rate(deal, selected_manager)

    await db.commit()

    logger.info(
        f"Deal {deal_id} auto-assigned to manager {selected_manager.display_name} "
        f"(id={selected_manager.id})"
    )

    return True


async def check_and_assign_warm_deals(db: AsyncSession) -> int:
    """
    Check for unassigned warm deals and assign them.

    Called periodically by the scheduler.

    Returns:
        Number of deals assigned
    """
    # Find unassigned warm deals
    result = await db.execute(
        select(DetectedDeal.id)
        .where(
            and_(
                DetectedDeal.status == DealStatus.WARM,
                DetectedDeal.manager_id.is_(None),
            )
        )
        .limit(10)  # Process in batches
    )
    deal_ids = [row[0] for row in result.all()]

    assigned_count = 0
    for deal_id in deal_ids:
        if await assign_deal_to_manager(deal_id, db):
            assigned_count += 1

    if assigned_count > 0:
        logger.info(f"Auto-assigned {assigned_count} warm deals")

    return assigned_count
