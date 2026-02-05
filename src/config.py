"""
Application configuration using Pydantic Settings.
All environment variables are loaded from .env file.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://user:pass@localhost:5432/arbion",
        description="PostgreSQL connection string (async)"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def convert_database_url(cls, v: str) -> str:
        """Convert standard postgres URL to asyncpg format."""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Authentication
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT token signing"
    )
    jwt_expire_hours: int = Field(
        default=12,
        description="JWT token expiration time in hours"
    )
    owner_username: str = Field(
        default="admin",
        description="Owner account username (created on first startup)"
    )
    owner_password: str = Field(
        default="admin",
        description="Owner account password (created on first startup)"
    )

    # Telegram
    tg_api_id: int = Field(
        default=0,
        description="Telegram API ID"
    )
    tg_api_hash: str = Field(
        default="",
        description="Telegram API Hash"
    )
    tg_session_string: str = Field(
        default="",
        description="Telethon session string"
    )

    # OpenAI
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key"
    )

    # Pinecone
    pinecone_api_key: str = Field(
        default="",
        description="Pinecone API key"
    )
    pinecone_index: str = Field(
        default="arbion-products",
        description="Pinecone index name"
    )
    pinecone_environment: str = Field(
        default="us-east-1",
        description="Pinecone environment"
    )

    # Supabase (optional)
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase project URL"
    )
    supabase_key: Optional[str] = Field(
        default=None,
        description="Supabase service role key"
    )
    storage_bucket: str = Field(
        default="chat-media",
        description="Supabase storage bucket name"
    )

    # Application
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    is_production: bool = Field(
        default=False,
        description="Production mode flag"
    )

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.database_url.replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
