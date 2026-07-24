from __future__ import annotations

import re
import time
from typing import Any

from minince.infrastructure.ssh.base import SSHConfig


class ParamikoSSHConnection:
    """基于 Paramiko 的真实 SSH 连接实现。

    支持华为 VRP 交互式 shell，能够：
    - 识别设备提示符（<HOSTNAME> 或 [HOSTNAME]）
    - 处理分页（---- More ----）
    - 去除命令回显
    - 支持 screen-length 0 禁用分页
    """

    # 匹配华为 VRP 提示符：<hostname> 或 [hostname]
    _PROMPT_RE = re.compile(r"[<\[][^<>\[\]]+[>\]]\s*$")

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._client: Any = None
        self._shell: Any = None
        self._hostname: str = ""

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

        # 启用交互式 shell
        self._shell = self._client.invoke_shell(
            term="vt100",
            width=200,
            height=1000,
        )

        # 等待 shell 就绪并读取欢迎信息
        time.sleep(1)
        self._read_until_prompt(timeout=10)

        # 禁用分页
        self._disable_paging()

        self._connected = True

    def disconnect(self) -> None:
        if self._shell:
            try:
                self._shell.close()
            except Exception:
                pass
        if self._client:
            self._client.close()
        self._connected = False
        self._shell = None
        self._client = None

    def send_command(self, command: str, read_timeout: int | None = None) -> str:
        if not self._connected or self._shell is None:
            raise ConnectionError("Not connected")

        timeout = read_timeout or self.config.timeout
        self._shell.send(command + "\n")
        output = self._read_until_prompt(timeout=timeout)

        # 去除命令回显：第一行通常就是发送的命令
        lines = output.split("\n")
        if lines and command.strip() in lines[0]:
            lines = lines[1:]

        # 去除最后的提示符行
        while lines and self._PROMPT_RE.match(lines[-1].strip()):
            lines = lines[:-1]

        return "\n".join(lines).strip()

    def send_config_set(self, config_commands: list[str]) -> str:
        results: list[str] = []
        for cmd in config_commands:
            result = self.send_command(cmd)
            if result:
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

    def _disable_paging(self) -> None:
        """禁用华为 VRP 的分页显示。"""
        # 用户视图下执行 screen-length 0 temporary
        self._shell.send("screen-length 0 temporary\n")
        time.sleep(0.5)
        # 清空缓冲区
        while self._shell.recv_ready():
            self._shell.recv(65535)

    def _read_until_prompt(self, timeout: int = 30) -> str:
        """读取输出直到遇到设备提示符。

        自动处理分页（---- More ----）和用户确认（Y/N）。
        """
        output = ""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._shell.recv_ready():
                chunk = self._shell.recv(65535).decode("utf-8", errors="replace")
                output += chunk

                # 处理分页：发送空格继续
                if "---- More ----" in output or "----More----" in output:
                    self._shell.send(" ")
                    # 清除分页标记
                    output = output.replace("---- More ----", "").replace("----More----", "")
                    continue

                # 处理确认提示：自动回复 y
                lower_out = output.lower()
                if "(y/n)" in lower_out or "[y/n]" in lower_out or "[y]:" in lower_out:
                    self._shell.send("y\n")
                    continue

                # 检查是否已经收到提示符
                lines = output.strip().split("\n")
                if lines:
                    last_line = lines[-1].strip()
                    if self._PROMPT_RE.match(last_line):
                        # 提取 hostname
                        match = re.search(r"[<\[]([^<>\[\]]+)[>\]]", last_line)
                        if match:
                            self._hostname = match.group(1)
                        break
            else:
                time.sleep(0.1)
                # 如果已经有输出且没有新数据，再等一会
                if output:
                    time.sleep(0.3)
                    if not self._shell.recv_ready():
                        break

        return output
