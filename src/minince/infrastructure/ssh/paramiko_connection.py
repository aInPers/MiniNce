from __future__ import annotations

import time
from typing import Any

from minince.infrastructure.ssh.base import SSHConfig


class ParamikoSSHConnection:
    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._client: Any = None
        self._shell: Any = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        import paramiko

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self._client.connect(
            hostname=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            timeout=self.config.timeout,
            banner_timeout=self.config.banner_timeout,
            auth_timeout=self.config.auth_timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        self._shell = self._client.invoke_shell()
        time.sleep(1)
        self._connected = True

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
        self._connected = False

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        if not self._connected or self._shell is None:
            raise ConnectionError("Not connected")

        timeout = read_timeout or self.config.timeout
        self._shell.send(command + "\n")

        output = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._shell.recv_ready():
                chunk = self._shell.recv(65535).decode("utf-8", errors="replace")
                output += chunk
            else:
                time.sleep(0.1)
                if output and self._shell.recv_ready() is False:
                    time.sleep(0.3)
                    if not self._shell.recv_ready():
                        break

        return output.strip()

    def send_config_set(self, config_commands: list[str]) -> str:
        results: list[str] = []
        for cmd in config_commands:
            result = self.send_command(cmd)
            results.append(result)
        return "\n".join(results)

    def send_command_timing(self, command: str) -> str:
        return self.send_command(command)

    def save_config(self) -> str:
        return self.send_command("save force")

    def __enter__(self) -> ParamikoSSHConnection:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()
