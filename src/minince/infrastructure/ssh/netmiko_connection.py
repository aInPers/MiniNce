from __future__ import annotations

from typing import Any

from minince.infrastructure.ssh.base import SSHConfig


class NetmikoSSHConnection:
    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._connection: Any = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        from netmiko import ConnectHandler

        device_type = self.config.device_type or self._detect_device_type()

        self._connection = ConnectHandler(
            device_type=device_type,
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            timeout=self.config.timeout,
            banner_timeout=self.config.banner_timeout,
            auth_timeout=self.config.auth_timeout,
            auto_add_host=True,
        )

        if self.config.enable_password:
            self._connection.enable()

        self._connected = True

    def disconnect(self) -> None:
        if self._connection:
            self._connection.disconnect()
        self._connected = False

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        if "display" in command.lower() or "show" in command.lower():
            return self._connection.send_command(command, read_timeout=read_timeout or self.config.timeout)
        else:
            return self._connection.send_command_timing(command)

    def send_config_set(self, config_commands: list[str]) -> str:
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        return self._connection.send_config_set(config_commands)

    def send_command_timing(self, command: str) -> str:
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        return self._connection.send_command_timing(command)

    def save_config(self) -> str:
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        return self._connection.save_config()

    def __enter__(self) -> NetmikoSSHConnection:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()

    def _detect_device_type(self) -> str:
        if self.config.device_type:
            return self.config.device_type

        return "hp_comware"
