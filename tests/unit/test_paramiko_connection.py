from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from minince.infrastructure.ssh.base import SSHConfig
from minince.infrastructure.ssh.paramiko_connection import ParamikoSSHConnection


@pytest.fixture
def mock_paramiko(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock, MagicMock]:
    """注入 mock paramiko 模块，使 connect() 内的局部 import 拿到 mock。

    返回 (paramiko, client, shell) 三元组，便于断言。
    """
    paramiko = MagicMock()

    client = MagicMock()
    paramiko.SSHClient.return_value = client

    shell = MagicMock()
    client.invoke_shell.return_value = shell
    # _read_until_prompt 首次 recv_ready 返回 True 并给出一个匹配提示符的输出，
    # 随后返回 False，使读取循环立即结束。
    shell.recv_ready.side_effect = [True, False, False]
    shell.recv.return_value = b"<HOSTNAME> "

    # AutoAddPolicy / RejectPolicy 需可调用，返回可区分的 mock 实例
    paramiko.AutoAddPolicy = MagicMock(name="AutoAddPolicy")
    paramiko.RejectPolicy = MagicMock(name="RejectPolicy")

    monkeypatch.setitem(sys.modules, "paramiko", paramiko)
    # 跳过 connect() 中的真实 sleep，避免测试等待
    monkeypatch.setattr(
        "minince.infrastructure.ssh.paramiko_connection.time.sleep",
        lambda *_args: None,
    )
    return paramiko, client, shell


class TestParamikoHostKeyPolicy:
    def test_connect_loads_system_host_keys(self, mock_paramiko: tuple) -> None:
        _paramiko, client, _shell = mock_paramiko
        conn = ParamikoSSHConnection(SSHConfig(host="10.0.0.2", username="admin", password="x"))
        conn.connect()

        # 关键修复：连接前必须加载系统已知主机密钥，否则 RejectPolicy 无密钥可校验
        client.load_system_host_keys.assert_called_once()

    def test_connect_uses_reject_policy_by_default(self, mock_paramiko: tuple) -> None:
        paramiko, client, _shell = mock_paramiko
        conn = ParamikoSSHConnection(SSHConfig(host="10.0.0.2", auto_add_host_key=False))
        conn.connect()

        client.set_missing_host_key_policy.assert_called_once()
        policy = client.set_missing_host_key_policy.call_args[0][0]
        assert policy is paramiko.RejectPolicy.return_value

    def test_connect_uses_auto_add_policy_when_enabled(self, mock_paramiko: tuple) -> None:
        paramiko, client, _shell = mock_paramiko
        conn = ParamikoSSHConnection(SSHConfig(host="10.0.0.2", auto_add_host_key=True))
        conn.connect()

        client.set_missing_host_key_policy.assert_called_once()
        policy = client.set_missing_host_key_policy.call_args[0][0]
        assert policy is paramiko.AutoAddPolicy.return_value

    def test_connect_passes_host_and_credentials(self, mock_paramiko: tuple) -> None:
        _paramiko, client, _shell = mock_paramiko
        conn = ParamikoSSHConnection(
            SSHConfig(host="10.0.0.2", port=2222, username="admin", password="secret")
        )
        conn.connect()

        client.connect.assert_called_once()
        kwargs = client.connect.call_args.kwargs
        assert kwargs["hostname"] == "10.0.0.2"
        assert kwargs["port"] == 2222
        assert kwargs["username"] == "admin"
        assert kwargs["password"] == "secret"
        assert kwargs["look_for_keys"] is False
        assert kwargs["allow_agent"] is False
