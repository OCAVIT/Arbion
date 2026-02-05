"""
Authentication middleware for role-based route protection.
"""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.jwt import get_token_from_cookie, verify_token

logger = logging.getLogger(__name__)

# Routes that don't require authentication
PUBLIC_ROUTES = {
    "/",
    "/login",
    "/api/auth/login",
    "/api/health",
    "/api/health/ready",
    "/api/health/live",
    "/favicon.ico",
}

# Route prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/static/",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces role-based access control.

    - /admin/* routes require owner role
    - /panel/* routes require owner or manager role
    - /api/admin/* routes require owner role
    - /api/panel/* routes require owner or manager role
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        path = request.url.path

        # Allow public routes
        if path in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Get token and verify
        token = get_token_from_cookie(request)
        payload = verify_token(token) if token else None

        # Check if authentication is required
        requires_auth = (
            path.startswith("/admin")
            or path.startswith("/panel")
            or path.startswith("/api/admin")
            or path.startswith("/api/panel")
        )

        if requires_auth and not payload:
            # Not authenticated - redirect to login for web routes
            if not path.startswith("/api/"):
                return RedirectResponse(url="/login", status_code=302)
            # Return 401 for API routes
            return Response(
                content='{"detail": "Not authenticated"}',
                status_code=401,
                media_type="application/json",
            )

        if payload:
            role = payload.get("role")

            # Check /admin routes - owner only
            if path.startswith("/admin") or path.startswith("/api/admin"):
                if role != "owner":
                    if not path.startswith("/api/"):
                        return RedirectResponse(url="/panel", status_code=302)
                    return Response(
                        content='{"detail": "Owner access required"}',
                        status_code=403,
                        media_type="application/json",
                    )

            # Check /panel routes - owner or manager
            if path.startswith("/panel") or path.startswith("/api/panel"):
                if role not in ("owner", "manager"):
                    if not path.startswith("/api/"):
                        return RedirectResponse(url="/login", status_code=302)
                    return Response(
                        content='{"detail": "Access denied"}',
                        status_code=403,
                        media_type="application/json",
                    )

        return await call_next(request)
