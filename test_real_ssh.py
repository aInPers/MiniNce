"""真实设备 SSH 连接测试脚本

使用方法:
  py test_real_ssh.py --host 192.168.1.1 --username admin --password YourPassword

这会:
  1. 通过 SSH 连接到您的华为路由器
  2. 执行 display version 命令
  3. 执行 display vlan 命令
  4. 创建 VLAN 100（测试用）
  5. 验证 VLAN 100 是否存在
  6. 删除 VLAN 100（清理）
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from minince.infrastructure.ssh.base import SSHConfig
from minince.infrastructure.ssh.paramiko_connection import ParamikoSSHConnection


def test_connection(host: str, port: int, username: str, password: str) -> bool:
    """测试真实 SSH 连接。"""
    print(f"\n{'='*60}")
    print(f"正在连接 {host}:{port} (用户: {username})")
    print(f"{'='*60}")

    config = SSHConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        timeout=30,
    )

    conn = ParamikoSSHConnection(config)

    try:
        conn.connect()
        print("✅ SSH 连接成功！")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return False

    # 测试 1: display version
    print("\n--- 测试 1: display version ---")
    try:
        output = conn.send_command("display version")
        print(f"命令输出:\n{output[:500]}")
        if output and len(output) > 10:
            print("✅ display version 成功")
        else:
            print("⚠️ display version 返回为空")
    except Exception as e:
        print(f"❌ display version 失败: {e}")

    # 测试 2: display vlan
    print("\n--- 测试 2: display vlan ---")
    try:
        output = conn.send_command("display vlan")
        print(f"命令输出:\n{output[:500]}")
        if output:
            print("✅ display vlan 成功")
        else:
            print("⚠️ display vlan 返回为空")
    except Exception as e:
        print(f"❌ display vlan 失败: {e}")

    # 测试 3: 进入系统视图并创建 VLAN
    print("\n--- 测试 3: 创建 VLAN 999 (测试) ---")
    try:
        output = conn.send_config_set([
            "system-view",
            "vlan 999",
            "name TEST_BY_MININCE",
            "quit",
            "quit",
        ])
        print(f"命令输出:\n{output}")
        print("✅ VLAN 创建命令已发送")
    except Exception as e:
        print(f"❌ VLAN 创建失败: {e}")

    # 测试 4: 验证 VLAN 是否创建成功
    print("\n--- 测试 4: 验证 VLAN 999 ---")
    try:
        output = conn.send_command("display vlan 999")
        print(f"命令输出:\n{output}")
        if "999" in output:
            print("✅ VLAN 999 验证成功 - 已在设备上创建！")
        else:
            print("⚠️ VLAN 999 未在输出中找到")
    except Exception as e:
        print(f"❌ VLAN 验证失败: {e}")

    # 测试 5: 清理 - 删除 VLAN 999
    print("\n--- 测试 5: 删除 VLAN 999 (清理) ---")
    try:
        output = conn.send_config_set([
            "system-view",
            "undo vlan 999",
            "quit",
        ])
        print(f"命令输出:\n{output}")
        print("✅ VLAN 999 已删除")
    except Exception as e:
        print(f"❌ VLAN 删除失败: {e}")

    # 测试 6: 保存配置
    print("\n--- 测试 6: 保存配置 ---")
    try:
        output = conn.save_config()
        print(f"命令输出:\n{output}")
        print("✅ 配置已保存")
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")

    conn.disconnect()
    print(f"\n{'='*60}")
    print("SSH 连接测试完成！")
    print(f"{'='*60}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="真实设备 SSH 连接测试")
    parser.add_argument("--host", required=True, help="设备 IP 地址")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口")
    parser.add_argument("--username", default="admin", help="SSH 用户名")
    parser.add_argument("--password", required=True, help="SSH 密码")

    args = parser.parse_args()

    success = test_connection(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
    )

    sys.exit(0 if success else 1)
