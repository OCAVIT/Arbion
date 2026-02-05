"""Admin audit log API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import AuditAction, AuditLog, User
from src.schemas.dashboard import AuditLogListResponse, AuditLogResponse

router = APIRouter(prefix="/audit")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def audit_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render audit log page."""
    return templates.TemplateResponse(
        "admin/audit.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """List audit logs with filters."""
    query = select(AuditLog).options(selectinload(AuditLog.user))

    # Apply filters
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    if action:
        query = query.where(AuditLog.action == action)

    if target_type:
        query = query.where(AuditLog.target_type == target_type)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting and pagination
    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                username=log.user.username if log.user else "Unknown",
                display_name=log.user.display_name if log.user else "Unknown",
                action=log.action.value,
                target_type=log.target_type,
                target_id=log.target_id,
                metadata=log.action_metadata,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total or 0,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.get("/actions")
async def list_audit_actions(
    current_user: User = Depends(require_owner),
):
    """List all possible audit actions."""
    return {
        "actions": [action.value for action in AuditAction]
    }
