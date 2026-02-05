"""
Background job definitions using APScheduler.

Jobs include:
- Deal auto-assignment
- Outbox processing
- Chat discovery (placeholder)
- Message parsing (placeholder)
- Deal matching (placeholder)
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.db import get_db_context
from src.services.deal_router import check_and_assign_warm_deals

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def deal_assignment_job():
    """Check and auto-assign warm deals."""
    logger.debug("Running deal assignment job")
    try:
        async with get_db_context() as db:
            assigned = await check_and_assign_warm_deals(db)
            if assigned:
                logger.info(f"Deal assignment job: assigned {assigned} deals")
    except Exception as e:
        logger.error(f"Deal assignment job error: {e}")


def setup_scheduler():
    """
    Configure and add all scheduled jobs.

    Called during application startup.
    """
    # Deal auto-assignment - run every minute
    scheduler.add_job(
        deal_assignment_job,
        trigger=IntervalTrigger(minutes=1),
        id="deal_assignment",
        name="Auto-assign warm deals",
        replace_existing=True,
    )

    # TODO: Add other jobs when services are implemented:
    # - chat_discovery_job (interval from settings)
    # - message_parser_job (interval from settings)
    # - deal_matcher_job (interval from settings)
    # - ai_negotiator_job (interval from settings)

    logger.info("Scheduler configured with jobs")
