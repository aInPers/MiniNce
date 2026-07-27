from __future__ import annotations

import json
from typing import Any, Iterator


class DeviceConfig:
    """设备配置类。

    以键值对形式存储配置项，支持 JSON 序列化与反序列化。
    键为配置项名称（字符串），值为配置内容（任意可 JSON 序列化的对象）。

    用途：
    - ``getAllConfigs`` 返回设备所有配置段（键为段名，值为配置文本或子字典）
    - ``getConfig(name)`` 返回单个配置段
    - ``pushConfig(config)`` 接收待下发的配置
    - ``getInterfaceConfig`` / ``setInterfaceConfig`` 用于接口级配置
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data) if data else {}

    # ------------------------------------------------------------------
    # 键值操作
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """获取指定键的值，不存在时返回默认值。"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置指定键的值。"""
        self._data[key] = value

    def remove(self, key: str) -> None:
        """移除指定键。"""
        self._data.pop(key, None)

    def has(self, key: str) -> bool:
        """判断是否包含指定键。"""
        return key in self._data

    def keys(self) -> list[str]:
        """返回所有键。"""
        return list(self._data.keys())

    def items(self) -> list[tuple[str, Any]]:
        """返回所有键值对。"""
        return list(self._data.items())

    def to_dict(self) -> dict[str, Any]:
        """返回内部字典的副本。"""
        return dict(self._data)

    # ------------------------------------------------------------------
    # 序列化与反序列化
    # ------------------------------------------------------------------
    def serialize(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self._data, ensure_ascii=False, indent=2)

    @classmethod
    def deserialize(cls, json_str: str) -> "DeviceConfig":
        """从 JSON 字符串反序列化为 DeviceConfig 实例。

        Args:
            json_str: JSON 格式的配置字符串

        Returns:
            反序列化后的 DeviceConfig 实例

        Raises:
            ValueError: JSON 内容不是对象（字典）时
            json.JSONDecodeError: JSON 格式无效时
        """
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError(
                f"反序列化失败：期望 JSON 对象，实际为 {type(data).__name__}"
            )
        return cls(data)

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DeviceConfig):
            return NotImplemented
        return self._data == other._data

    def __repr__(self) -> str:
        return f"DeviceConfig({self._data!r})"
