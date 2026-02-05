"""
Health check endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """
    Basic health check.

    Returns 200 if the service is running.
    """
    return {"status": "healthy", "service": "arbion"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Readiness check with database connectivity.

    Returns 200 if the service is ready to handle requests.
    """
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
        return {
            "status": "not_ready",
            "database": db_status,
        }

    return {
        "status": "ready",
        "database": db_status,
    }


@router.get("/live")
async def liveness_check():
    """
    Liveness check.

    Returns 200 if the service is alive.
    Used by Kubernetes/Railway to determine if the container should be restarted.
    """
    return {"status": "alive"}
