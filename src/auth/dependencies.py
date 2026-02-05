"""
FastAPI dependencies for authentication.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import get_token_from_cookie, verify_token
from src.db import get_db
from src.models import User, UserRole


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get current user from JWT cookie if present.

    Returns None if no valid token found (doesn't raise error).
    Use for routes that work with or without authentication.
    """
    token = get_token_from_cookie(request)
    if not token:
        return None

    payload = verify_token(token)
    if not payload:
        return None

    user = await db.execute(
        select(User).where(User.id == payload["user_id"])
    )
    user = user.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current authenticated user.

    Raises 401 if not authenticated or user is inactive.
    """
    token = get_token_from_cookie(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await db.execute(
        select(User).where(User.id == payload["user_id"])
    )
    user = user.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def require_owner(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the current user to be an owner.

    Raises 403 if user is not an owner.
    """
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )
    return current_user


async def require_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the current user to be a manager (or owner).

    Owners can access manager routes for testing/debugging.
    Raises 403 if user is neither owner nor manager.
    """
    if current_user.role not in (UserRole.OWNER, UserRole.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return current_user


async def require_active_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the current user to be an active manager.

    Unlike require_manager, this does NOT allow owners.
    Use for manager-specific features that owners shouldn't access.
    """
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return current_user
