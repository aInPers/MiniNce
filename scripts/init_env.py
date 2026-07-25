"""生成 MiniNCE .env 配置文件。

由 start.bat 调用，确保 .env 以 UTF-8 编码写入，避免 PowerShell/CMD
在中文系统下因代码页问题导致 python-dotenv 读取时 UnicodeDecodeError。

用法：
    py scripts/init_env.py <environment> <debug> <host> <port>
    py scripts/init_env.py --ensure-key            # 仅在 .env 缺少有效密钥时补充
"""
from __future__ import annotations

import sys
from pathlib import Path


def _generate_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def _build_content(environment: str, debug: str, host: str, port: str, key: str) -> str:
    """构造 .env 文件内容（纯 UTF-8，含中文注释）。"""
    lines = [
        "# MiniNCE 环境配置文件",
        "# 由 scripts/init_env.py 自动生成，请妥善保管 ENCRYPTION_KEY",
        "# 丢失 ENCRYPTION_KEY 将无法解密已保存的设备密码",
        "",
        f"ENVIRONMENT={environment}",
        f"DEBUG={debug}",
        f"HOST={host}",
        f"PORT={port}",
        "",
        "DATABASE_URL=sqlite:///./minince.db",
        "",
        "LOG_LEVEL=INFO",
        "LOG_FORMAT=json",
        "LOG_FILE=logs/minince.log",
        "",
        f"ENCRYPTION_KEY={key}",
        "",
        "SSH_TIMEOUT=30",
        "SSH_PORT=22",
    ]
    return "\n".join(lines) + "\n"


def generate(env_file: Path, environment: str, debug: str, host: str, port: str) -> str:
    """生成全新的 .env 文件并返回密钥。"""
    key = _generate_key()
    content = _build_content(environment, debug, host, port, key)
    env_file.write_text(content, encoding="utf-8", newline="\n")
    return key


def ensure_key(env_file: Path) -> str | None:
    """若 .env 缺少有效的 ENCRYPTION_KEY 则补充，返回新密钥；否则返回 None。"""
    if not env_file.exists():
        return None

    try:
        text = env_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 文件编码损坏，触发重新生成
        return None

    existing_key: str | None = None
    for line in text.splitlines():
        if line.startswith("ENCRYPTION_KEY="):
            existing_key = line.split("=", 1)[1].strip()
            break

    if existing_key and existing_key != "your-encryption-key-here":
        return None  # 已有有效密钥

    key = _generate_key()
    # 追加到文件末尾（UTF-8 编码）
    with env_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\nENCRYPTION_KEY={key}\n")
    return key


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: py scripts/init_env.py <environment> <debug> <host> <port>")
        print("       py scripts/init_env.py --ensure-key")
        return 1

    env_file = Path(".env")

    if sys.argv[1] == "--ensure-key":
        new_key = ensure_key(env_file)
        if new_key:
            print(f"APPENDED_KEY={new_key}")
        else:
            print("NO_CHANGE")
        return 0

    if len(sys.argv) < 5:
        print("Usage: py scripts/init_env.py <environment> <debug> <host> <port>")
        return 1

    environment, debug, host, port = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    key = generate(env_file, environment, debug, host, port)
    print(f"GENERATED_KEY={key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
