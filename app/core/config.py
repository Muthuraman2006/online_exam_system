import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    # REQUIRED — no defaults, must come from .env or environment
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REDIS_URL: str = "redis://localhost:6379/0"
    DEBUG: bool = False
    
    # CORS - comma-separated origins string (parsed via property)
    CORS_ORIGINS: str = "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8000,http://localhost:8000"
    
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list. Supports comma-separated env var.
        Falls back to ["*"] when DEBUG is True and no origins are set."""
        if not self.CORS_ORIGINS:
            return ["*"] if self.DEBUG else []
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
    
    # Exam settings
    MAX_EXAM_DURATION_MINUTES: int = 180
    AUTO_SAVE_INTERVAL_SECONDS: int = 30
    GRACE_PERIOD_SECONDS: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
