from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    timeout: int = 30
    device_type: str = ""
    enable_password: str = ""
    banner_timeout: int = 5
    auth_timeout: int = 30
    auto_add_host_key: bool = True


@runtime_checkable
class SSHConnection(Protocol):
    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def send_command(self, command: str, read_timeout: int | None = None) -> str: ...

    def send_config_set(self, config_commands: list[str]) -> str: ...

    def send_command_timing(self, command: str) -> str: ...

    def save_config(self) -> str: ...

    def __enter__(self) -> SSHConnection: ...

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...
