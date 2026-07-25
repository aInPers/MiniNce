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

    安全说明：
    - 默认使用 RejectPolicy 拒绝未知主机密钥
    - 仅在 SSHConfig.auto_add_host_key=True 时使用 AutoAddPolicy
    - 不再无条件自动回答 Y/N 提示，仅对 save 命令的确认回复 y
    """

    # 匹配华为 VRP 提示符：<hostname> 或 [hostname]
    _PROMPT_RE = re.compile(r"[<\[][^<>\[\]]+[>\]]\s*$")

    # 允许自动回复 Y/N 的安全命令白名单（仅 save 类命令）
    _SAFE_CONFIRM_COMMANDS = {"save", "save force"}

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._connected = False
        self._client: Any = None
        self._shell: Any = None
        self._hostname: str = ""
        # 记录最后发送的命令，用于判断 Y/N 提示是否为安全命令的确认
        self._last_command: str = ""

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        import paramiko

        self._client = paramiko.SSHClient()

        # 根据配置选择主机密钥策略
        if self.config.auto_add_host_key:
            # 仅在显式开启首次发现模式时自动接受主机密钥
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            # 默认拒绝未知主机密钥，防止中间人攻击
            self._client.set_missing_host_key_policy(paramiko.RejectPolicy())

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
        self._last_command = command.strip()
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
        Y/N 确认仅对 save 类安全命令自动回复，其他命令的确认提示将保留在输出中。
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

                # 处理确认提示：仅对安全命令（save）自动回复 y
                lower_out = output.lower()
                if "(y/n)" in lower_out or "[y/n]" in lower_out or "[y]:" in lower_out:
                    if self._last_command in self._SAFE_CONFIRM_COMMANDS:
                        # save 命令的确认提示，安全回复 y
                        self._shell.send("y\n")
                        output = output.replace("(y/n)", "").replace("[y/n]", "").replace("[y]:", "")
                        continue
                    # 非安全命令的确认提示，不自动回复，保留在输出中供业务层处理
                    # 跳出循环，让调用方看到确认提示
                    break

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
