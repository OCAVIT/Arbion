"""
Authentication API endpoints.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user_optional
from src.auth.jwt import create_access_token
from src.config import settings
from src.db import get_db
from src.models import AuditAction, User, UserRole
from src.schemas.auth import LoginRequest, LoginResponse
from src.utils.audit import get_client_ip, log_action
from src.utils.password import verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])
templates = Jinja2Templates(directory="src/templates")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
):
    """Render login page."""
    # Redirect if already logged in
    if current_user:
        if current_user.role == UserRole.OWNER:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/panel", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@router.get("/m/{invite_token}", response_class=HTMLResponse, include_in_schema=False)
async def manager_login_page(
    request: Request,
    invite_token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    """
    Render login page for manager with pre-filled username.

    This is a personalized login link for each manager.
    The invite_token identifies the manager but doesn't auto-login.
    """
    # Redirect if already logged in
    if current_user:
        if current_user.role == UserRole.OWNER:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/panel", status_code=302)

    # Find manager by invite token
    result = await db.execute(
        select(User).where(
            User.invite_token == invite_token,
            User.role == UserRole.MANAGER,
        )
    )
    manager = result.scalar_one_or_none()

    if not manager:
        # Invalid token - redirect to normal login
        return RedirectResponse(url="/login", status_code=302)

    if not manager.is_active:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Ваш аккаунт деактивирован. Обратитесь к администратору.",
                "prefill_username": None,
            },
        )

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "prefill_username": manager.username,
            "manager_name": manager.display_name,
        },
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and set JWT cookie.

    Returns redirect URL based on user role:
    - owner -> /admin
    - manager -> /panel
    """
    # Find user
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()

    # Verify credentials
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Check if active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create JWT token
    token = create_access_token(user.id, user.role.value)

    # Set httpOnly cookie
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
    )

    # Update last active
    user.last_active_at = datetime.now(timezone.utc)

    # Log login action
    await log_action(
        db=db,
        user_id=user.id,
        action=AuditAction.LOGIN,
        ip_address=get_client_ip(request),
    )

    # Determine redirect URL
    redirect_url = "/admin" if user.role == UserRole.OWNER else "/panel"

    return LoginResponse(
        success=True,
        message="Login successful",
        redirect_url=redirect_url,
        role=user.role.value,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    """
    Clear JWT cookie and log out.
    """
    # Log logout action if user was authenticated
    if current_user:
        await log_action(
            db=db,
            user_id=current_user.id,
            action=AuditAction.LOGOUT,
            ip_address=get_client_ip(request),
        )

    # Clear cookie
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )

    return {"success": True, "message": "Logged out"}
