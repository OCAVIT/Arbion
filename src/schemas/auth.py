"""Authentication schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request body."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response."""

    success: bool
    message: str
    redirect_url: str = Field(default="/")
    role: str = Field(default="")


class TokenPayload(BaseModel):
    """JWT token payload."""

    user_id: int
    role: str
