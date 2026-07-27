"""一次性诊断脚本：验证 MiniNCE 数据库里的设备凭据是否能正常解密并连接 SSH。

使用方法:
  py diagnose_device.py                    # 列出所有设备
  py diagnose_device.py --device-id 1      # 诊断指定设备
  py diagnose_device.py --device-id 1 --show-password  # 显示解密后的密码（谨慎使用）
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from minince.infrastructure.database.connection import SessionLocal
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager


def list_devices() -> None:
    db = SessionLocal()
    try:
        repo = DeviceRepository(db)
        devices = repo.get_all()
        if not devices:
            print("数据库里没有任何设备，请先去 Web UI 添加设备。")
            return
        print(f"共 {len(devices)} 台设备：")
        print(f"{'ID':<4}{'名称':<20}{'IP':<22}{'端口':<6}{'用户名':<15}{'类型'}")
        print("-" * 80)
        for d in devices:
            print(f"{d.id:<4}{d.name:<20}{d.management_ip:<22}{d.port:<6}{d.username:<15}{d.device_type}")
    finally:
        db.close()


def diagnose(device_id: int, show_password: bool) -> None:
    db = SessionLocal()
    try:
        repo = DeviceRepository(db)
        device = repo.get_by_id(device_id)
        if device is None:
            print(f"错误：设备 ID {device_id} 不存在")
            return

        print(f"\n=== 设备信息 ===")
        print(f"  ID:       {device.id}")
        print(f"  名称:     {device.name}")
        print(f"  IP:       {device.management_ip}")
        print(f"  端口:     {device.port}")
        print(f"  用户名:   {device.username}")
        print(f"  厂商:     {device.vendor}")
        print(f"  加密密码: {device.encrypted_password[:40]}...（共 {len(device.encrypted_password)} 字符）")

        # Step 1: 解密
        print(f"\n=== Step 1: 解密密码 ===")
        encryption = EncryptionManager()
        try:
            password = encryption.decrypt(device.encrypted_password)
            print(f"  解密成功，密码长度: {len(password)}")
            if show_password:
                print(f"  密码明文: {password!r}")
            else:
                print(f"  密码前 2 字符: {password[:2]!r}（用 --show-password 查看完整）")
        except Exception as e:
            print(f"  ❌ 解密失败: {e}")
            print(f"  这说明数据库里的密码字段无法用当前 EncryptionManager 解密。")
            print(f"  可能原因：")
            print(f"    1. 加密密钥已变更（重装/迁移环境）")
            print(f"    2. 密码字段被手动篡改")
            print(f"    3. EncryptionManager 实现不一致")
            return

        # Step 2: 测试 SSH 连接
        print(f"\n=== Step 2: 测试 SSH 连接 ===")
        try:
            import paramiko
        except ImportError:
            print("  ❌ 未安装 paramiko")
            return

        print(f"  paramiko 版本: {paramiko.__version__}")
        print(f"  目标: {device.management_ip}:{device.port} 用户={device.username}")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=device.management_ip,
                port=device.port,
                username=device.username,
                password=password,
                timeout=30,
                banner_timeout=5,
                auth_timeout=30,
                look_for_keys=False,
                allow_agent=False,
            )
            print(f"  ✅ SSH 连接成功")
            print(f"\n=== Step 3: 测试 invoke_shell ===")
            try:
                shell = client.invoke_shell(term="vt100", width=200, height=50)
                print(f"  ✅ invoke_shell 成功")
                shell.close()
            except Exception as e:
                print(f"  ❌ invoke_shell 失败: {e}")
            client.close()
            print(f"\n=== 诊断结论 ===")
            print(f"  数据库凭据完全正常，WebSocket 应该也能连。")
            print(f"  如果 Web UI 仍报错，请检查 Web 服务是否重启加载了新代码。")
        except paramiko.AuthenticationException as e:
            print(f"  ❌ 认证失败: {e}")
            print(f"\n=== 诊断结论 ===")
            print(f"  SSH 协议正常但用户名/密码被设备拒绝。")
            print(f"  解决方案：")
            print(f"    1. 用 ssh 命令行手动验证： ssh {device.username}@{device.management_ip}")
            print(f"    2. 如果命令行也连不上，说明设备密码已变更，请联系管理员重置")
            print(f"    3. 如果命令行能连，说明数据库里存的密码不对，请到 Web UI 编辑该设备，重新输入密码")
        except paramiko.SSHException as e:
            print(f"  ❌ SSH 协议错误: {e}")
            print(f"  异常类型: {type(e).__name__}")
            print(f"\n=== 诊断结论 ===")
            print(f"  算法协商或协议层问题。")
            print(f"  尝试用 ssh 命令行带传统算法选项连接：")
            print(f"    ssh -oKexAlgorithms=+diffie-hellman-group-exchange-sha1 "
                  f"-oHostKeyAlgorithms=+ssh-rsa -oCiphers=+aes128-cbc "
                  f"-omACs=+hmac-sha1 {device.username}@{device.management_ip}")
        except OSError as e:
            print(f"  ❌ 网络连接失败: {e}")
            print(f"\n=== 诊断结论 ===")
            print(f"  设备不可达。请检查：")
            print(f"    1. 设备是否开机")
            print(f"    2. IP 是否正确")
            print(f"    3. ping {device.management_ip} 是否通")
            print(f"    4. 防火墙是否拦截 {device.port} 端口")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断 MiniNCE 数据库设备凭据")
    parser.add_argument("--device-id", type=int, help="要诊断的设备 ID")
    parser.add_argument("--show-password", action="store_true", help="显示解密后的密码明文（谨慎使用）")
    args = parser.parse_args()

    if args.device_id is None:
        list_devices()
        print(f"\n使用 py diagnose_device.py --device-id <ID> 进行诊断")
        return 0

    diagnose(args.device_id, args.show_password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
