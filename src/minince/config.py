from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 已知的默认密钥，禁止在任何环境使用
_DEPRECATED_DEFAULT_KEY = "IGCMr1nmWE42wXtTzSpoBRVnyK0_EqkhrZuTCfuNcoo="

# 测试专用密钥（仅用于 development/testing 环境自动注入）
_TEST_KEY = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="


class Settings(BaseSettings):
    """MiniNCE 应用配置。

    安全说明：
    - encryption_key 必须显式配置，不再内置默认密钥
    - debug 默认关闭，host 默认绑定本地回环地址
    - 生产环境启动时会强制校验安全相关配置
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "MiniNCE"
    app_version: str = "0.1.0"

    # 环境标识：production 启动时会强制校验安全配置
    environment: Literal["development", "testing", "production"] = "production"

    # 默认安全：关闭 debug，仅监听本地回环
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = "sqlite:///./minince.db"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_file: str = "logs/minince.log"

    # 加密密钥：无默认值，必须通过环境变量或 .env 配置
    encryption_key: str = ""

    ssh_timeout: int = 30
    ssh_port: int = 22

    @model_validator(mode="after")
    def validate_security_config(self) -> Settings:
        """统一校验安全相关配置，根据环境应用不同规则。"""
        # 所有环境都禁止使用已知的默认密钥
        if self.encryption_key == _DEPRECATED_DEFAULT_KEY:
            raise ValueError(
                "The built-in default encryption key is prohibited. "
                "Please generate a new key via "
                "`py -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
                "and set it as ENCRYPTION_KEY in .env"
            )

        if self.environment == "production":
            # 生产环境强制配置加密密钥
            if not self.encryption_key:
                raise ValueError(
                    "ENCRYPTION_KEY must be configured in production environment. "
                    "Generate one via "
                    "`py -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`"
                )
            # 生产环境禁止开启 debug
            if self.debug:
                raise ValueError(
                    "Debug mode cannot be enabled in production environment. "
                    "Set DEBUG=false in .env or use environment=development."
                )
            # 生产环境禁止绑定到所有接口
            if self.host in ("0.0.0.0", "::"):
                raise ValueError(
                    "Binding to all interfaces (0.0.0.0) is prohibited in production. "
                    "Set HOST=127.0.0.1 or a specific interface in .env."
                )
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent.parent.parent


def _load_settings() -> Settings:
    """加载配置，测试/开发环境自动注入测试密钥避免启动失败。"""
    env = os.environ.get("ENVIRONMENT", "production").lower()
    if env in ("development", "testing"):
        # 开发/测试环境自动注入测试密钥（非默认密钥，不会触发校验）
        os.environ.setdefault("ENCRYPTION_KEY", _TEST_KEY)
    return Settings()


settings = _load_settings()
