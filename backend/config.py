"""
Configuration module for SupportLens backend.
Loads environment variables and provides database connection settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database settings
    database_host: str = "localhost"
    database_port: int = 3306
    database_name: str = "supportlens"
    database_user: str = "root"
    database_password: str = ""
    database_type: str = "mysql"  # mysql or postgresql

    # Gemini API settings
    gemini_api_key: str = ""

    # Application settings
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        """Construct database URL from settings."""
        if self.database_type == "postgresql":
            return (
                f"postgresql://{self.database_user}:{self.database_password}"
                f"@{self.database_host}:{self.database_port}/{self.database_name}"
            )
        # Default to MySQL
        return (
            f"mysql+pymysql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# SQLAlchemy Base for ORM models
Base = declarative_base()


def get_engine():
    """Create SQLAlchemy engine with current settings."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


def get_session_local():
    """Create session factory."""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Database dependency for FastAPI
def get_db():
    """Dependency that provides database session."""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
