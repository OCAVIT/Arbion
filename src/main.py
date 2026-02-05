"""
Arbion - Automated Deal Management System

Main FastAPI application with:
- Role-based authentication (owner/manager)
- Admin Dashboard
- Manager Panel
- Telegram integration via Telethon
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from src.api import admin_router, api_router, panel_router
from src.auth.dependencies import get_current_user_optional
from src.auth.middleware import AuthMiddleware
from src.config import settings
from src.db import AsyncSessionLocal, get_db_context
from src.models import SystemSetting, User, UserRole
from src.utils.password import hash_password

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup:
    - Creates owner account if not exists
    - Initializes default system settings

    Shutdown:
    - Cleanup tasks
    """
    logger.info("Starting Arbion...")

    async with get_db_context() as db:
        # Create owner account if not exists
        result = await db.execute(
            select(User).where(User.role == UserRole.OWNER)
        )
        owner = result.scalar_one_or_none()

        if not owner:
            logger.info("Creating owner account...")
            owner = User(
                username=settings.owner_username,
                password_hash=hash_password(settings.owner_password),
                role=UserRole.OWNER,
                display_name="Owner",
                is_active=True,
            )
            db.add(owner)
            logger.info(f"Owner account created: {settings.owner_username}")

        # Initialize default settings
        default_settings = {
            "target_chat_count": 100,
            "assignment_mode": "free_pool",
            "max_deals_per_manager": 15,
            "min_margin_threshold": 5.0,
            "parser_interval_minutes": 5,
            "matcher_interval_minutes": 10,
            "negotiator_interval_minutes": 15,
            "seed_queries": [],
        }

        for key, value in default_settings.items():
            existing = await db.get(SystemSetting, key)
            if not existing:
                db.add(SystemSetting(key=key, value={"v": value}))
                logger.info(f"Created default setting: {key}")

        await db.commit()

    logger.info("Arbion started successfully!")

    yield

    # Shutdown
    logger.info("Shutting down Arbion...")


# Create FastAPI application
app = FastAPI(
    title="Arbion",
    description="Automated Deal Management System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Templates
templates = Jinja2Templates(directory="src/templates")

# Include routers
app.include_router(api_router)  # /api/* endpoints
app.include_router(admin_router)  # /admin/* web interface
app.include_router(panel_router)  # /panel/* web interface


# Root redirect
@app.get("/", include_in_schema=False)
async def root(request: Request):
    """Redirect root to appropriate dashboard based on role."""
    async with get_db_context() as db:
        user = await get_current_user_optional(request, db)

    if user:
        if user.role == UserRole.OWNER:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/panel", status_code=302)

    return RedirectResponse(url="/login", status_code=302)


# Login page
@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Render login page."""
    async with get_db_context() as db:
        user = await get_current_user_optional(request, db)

    if user:
        if user.role == UserRole.OWNER:
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/panel", status_code=302)

    return templates.TemplateResponse(
        "login.html",
        {"request": request},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
    )
