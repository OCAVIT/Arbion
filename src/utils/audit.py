"""
Audit logging utilities.

All manager actions must be logged for security.
"""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditAction, AuditLog


async def log_action(
    db: AsyncSession,
    user_id: int,
    action: AuditAction,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    action_metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Log an auditable action.

    Args:
        db: Database session
        user_id: ID of the user performing the action
        action: Type of action being performed
        target_type: Type of entity affected (e.g., "deal", "chat")
        target_id: ID of the affected entity
        action_metadata: Additional context about the action
        ip_address: Client IP address

    Returns:
        Created AuditLog entry
    """
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        action_metadata=action_metadata,
        ip_address=ip_address,
    )
    db.add(log_entry)
    # Note: commit should happen in the calling context
    return log_entry


def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP from request.

    Handles X-Forwarded-For header for reverse proxy setups.
    """
    # Check for X-Forwarded-For header (Railway, nginx, etc.)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the list is the client
        return forwarded_for.split(",")[0].strip()

    # Fall back to direct client IP
    if hasattr(request, "client") and request.client:
        return request.client.host

    return None
