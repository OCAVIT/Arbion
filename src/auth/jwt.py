"""
JWT token management.

Tokens are stored in httpOnly cookies for security.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from src.config import settings

# JWT configuration
ALGORITHM = "HS256"
TOKEN_TYPE = "access"


def create_access_token(
    user_id: int,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: User's database ID
        role: User's role (owner/manager)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": TOKEN_TYPE,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict with 'sub' (user_id) and 'role',
        or None if token is invalid/expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )

        # Validate token type
        if payload.get("type") != TOKEN_TYPE:
            return None

        # Validate required fields
        user_id = payload.get("sub")
        role = payload.get("role")

        if not user_id or not role:
            return None

        return {
            "user_id": int(user_id),
            "role": role,
        }

    except JWTError:
        return None


def get_token_from_cookie(request) -> Optional[str]:
    """
    Extract JWT token from httpOnly cookie.

    Args:
        request: FastAPI Request object

    Returns:
        Token string or None
    """
    return request.cookies.get("access_token")
