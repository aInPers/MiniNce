from __future__ import annotations

from abc import ABC, abstractmethod

from minince.domain.devices.config import DeviceConfig
from minince.domain.devices.facts import ConnectionResult
from minince.shared.enums import ConnectionType, DeviceType


class NetworkDevice(ABC):
    """网络设备接口类。

    定义网络设备管理的标准接口，涵盖设备信息获取、配置管理、
    邻居发现、接口配置、连接管理等能力。各厂商设备实现类需继承
    本类并实现全部抽象方法。
    """

    # ------------------------------------------------------------------
    # 设备信息
    # ------------------------------------------------------------------
    @abstractmethod
    def get_type(self) -> DeviceType:
        """获取设备类型。

        Returns:
            设备类型枚举值（如 ROUTER、SWITCH）
        """

    @abstractmethod
    def get_vendor(self) -> str:
        """获取设备厂家。

        Returns:
            设备厂家名称（如 "HUAWEI"、"CISCO"）
        """

    @abstractmethod
    def get_model(self) -> str:
        """获取设备型号。

        Returns:
            设备型号字符串
        """

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------
    @abstractmethod
    def get_all_configs(self) -> DeviceConfig:
        """获取设备所有配置信息。

        Returns:
            包含全部配置的 DeviceConfig 实例
        """

    @abstractmethod
    def get_config(self, name: str) -> DeviceConfig:
        """获取对应配置。

        Args:
            name: 配置段名称（如 "ospf"、"vlan"、"interface GE0/0/0"）

        Returns:
            对应配置段的 DeviceConfig 实例
        """

    @abstractmethod
    def push_config(self, config: DeviceConfig) -> bool:
        """下发配置文件。

        根据配置内容逐条下发，途中若失败一次则返回失败并撤销
        （undo 逆序回滚）已执行成功的设置。

        Args:
            config: 待下发的设备配置

        Returns:
            True 表示全部下发成功，False 表示失败（已回滚）
        """

    # ------------------------------------------------------------------
    # 邻居发现
    # ------------------------------------------------------------------
    @abstractmethod
    def get_neighbors(self) -> list[tuple[str, str]]:
        """查看周边网络设备。

        Returns:
            周边网络设备列表，每个元素为 (设备名, IP) 二元组
        """

    # ------------------------------------------------------------------
    # 接口配置
    # ------------------------------------------------------------------
    @abstractmethod
    def get_interface_config(self, interface_name: str) -> DeviceConfig:
        """获取对应接口配置。

        Args:
            interface_name: 接口名称（如 "GE0/0/0"）

        Returns:
            接口配置的 DeviceConfig 实例
        """

    @abstractmethod
    def set_interface_config(
        self, interface_name: str, config: DeviceConfig
    ) -> bool:
        """设置对应接口配置。

        根据配置内容逐条下发，途中失败一次则返回失败并撤销
        （undo 逆序回滚）已执行成功的配置。

        Args:
            interface_name: 接口名称
            config: 接口配置

        Returns:
            True 表示设置成功，False 表示失败（已回滚）
        """

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    @abstractmethod
    def connect(self, connection_type: ConnectionType) -> ConnectionResult:
        """按照连接类型开始连接并返回连接信息。

        Args:
            connection_type: 连接类型（SSH、TELNET、CONSOLE）

        Returns:
            连接结果信息
        """

    @abstractmethod
    def set_credentials(self, username: str, password: str) -> None:
        """设置用户名与密码。

        Args:
            username: 用户名
            password: 密码
        """

    @abstractmethod
    def close(self) -> bool:
        """关闭连接。

        尝试关闭连接并返回关闭结果。

        Returns:
            True 表示关闭成功，False 表示关闭失败
        """
