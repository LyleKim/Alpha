"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    log_level: str


def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "alpha-backend"),
        app_env=os.getenv("APP_ENV", "local"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
