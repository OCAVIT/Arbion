"""
Tiered commission calculation for managers.

Rules:
- System lead (AI matched): 20% of margin
- Manager lead (brought by manager): 35% of margin
- Custom rate on manager overrides the default
"""

from decimal import Decimal

from src.models.deal import DetectedDeal
from src.models.user import User

# Default commission rates
SYSTEM_LEAD_RATE = Decimal("0.20")   # 20% for AI-found leads
MANAGER_LEAD_RATE = Decimal("0.35")  # 35% for manager-sourced leads


def calculate_commission_rate(deal: DetectedDeal, manager: User) -> Decimal:
    """Calculate the manager's commission rate for a deal.

    The rate is fixed at assignment time and saved to deal.manager_commission_rate
    so it doesn't change if the manager's rate is updated later.

    Args:
        deal: The deal being assigned
        manager: The manager being assigned to the deal

    Returns:
        Commission rate as a Decimal fraction (e.g. 0.20 = 20%)
    """
    if deal.lead_source == "manager":
        base_rate = MANAGER_LEAD_RATE
    else:
        base_rate = SYSTEM_LEAD_RATE

    # Custom rate on manager overrides the tier default
    if manager.commission_rate is not None and manager.commission_rate != Decimal("0.10"):
        # 0.10 is the old default — treat it as "not customised"
        return manager.commission_rate

    return base_rate
