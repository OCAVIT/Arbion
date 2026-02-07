"""AI Copilot schemas — lead cards and suggested responses for managers."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class LeadCardResponse(BaseModel):
    """Lead card for manager panel."""

    deal_id: int
    product: str
    niche: Optional[str] = None
    sell_price: float
    estimated_margin: float  # Owner doesn't show buy_price, but shows expected margin %
    volume: Optional[str] = None
    region: Optional[str] = None
    seller_city: Optional[str] = None
    ai_draft_seller: Optional[str] = None
    ai_draft_buyer: Optional[str] = None
    market_context: Optional[Dict] = None  # Parsed JSON
    created_at: datetime
    platform: str = "telegram"


class SuggestedResponses(BaseModel):
    """AI-suggested response variants for manager."""

    variants: List[str]  # 2-3 text variants
    margin_info: Optional[str] = None  # e.g. "Current margin: 3.5K/ton (7.3%)"
