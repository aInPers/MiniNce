from __future__ import annotations

from typing import Any

from minince.infrastructure.ssh.base import SSHConfig


class NetmikoSSHConnection:
    """基于 Netmiko 的 SSH 连接实现。

    安全说明：
    - 默认不自动接受主机密钥（auto_add_host=False）
    - 不再通过字符串包含判断命令类型，改为显式方法分类
    - 不再静默回退到 hp_comware，设备类型未知时报错
    """

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._connection: Any = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        from netmiko import ConnectHandler

        device_type = self._resolve_device_type()

        self._connection = ConnectHandler(
            device_type=device_type,
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            timeout=self.config.timeout,
            banner_timeout=self.config.banner_timeout,
            auth_timeout=self.config.auth_timeout,
            # 默认不自动接受主机密钥，避免中间人攻击
            auto_add_host=self.config.auto_add_host_key,
        )

        if self.config.enable_password:
            self._connection.enable()

        self._connected = True

    def disconnect(self) -> None:
        if self._connection:
            self._connection.disconnect()
        self._connected = False

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        """发送查询类命令（display/show），等待完整输出返回。

        Args:
            command: 查询命令，如 display vlan 100
            read_timeout: 读取超时秒数
        """
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        return self._connection.send_command(
            command,
            read_timeout=read_timeout or self.config.timeout,
        )

    def send_config_set(self, config_commands: list[str]) -> str:
        """发送配置类命令集合，自动进入和退出配置模式。

        Args:
            config_commands: 配置命令列表
        """
        if not self._connected or self._connection is None:
            raise ConnectionError("Not connected")

        return self._connection.send_config_set(config_commands)

    def send_command_timing(self, command: str) -> str:
        """发送交互式命令，基于时间间隔读取输出。

        用于需要交互确认的命令，调用方需自行处理 Y/N 提示。

        Args:
            command: 交互式命令
        """
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

    def _resolve_device_type(self) -> str:
        """解析 Netmiko 设备类型。

        不再静默回退到 hp_comware，设备类型未知时显式报错。
        """
        if self.config.device_type:
            return self.config.device_type

        raise ValueError(
            "Netmiko device_type must be explicitly configured. "
            "For Huawei VRP devices, set device_type='huawei'."
        )
