from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "MiniNCE"
    app_version: str = "0.1.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite:///./minince.db"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_file: str = "logs/minince.log"

    encryption_key: str = "IGCMr1nmWE42wXtTzSpoBRVnyK0_EqkhrZuTCfuNcoo="

    ssh_timeout: int = 30
    ssh_port: int = 22

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent.parent.parent


settings = Settings()
