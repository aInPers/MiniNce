from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.infrastructure.ssh.base import SSHConfig
from minince.infrastructure.ssh.mock_connection import MockSSHConnection
from minince.infrastructure.ssh.paramiko_connection import ParamikoSSHConnection

router = APIRouter(prefix="/manual-config", tags=["manual-config"])

TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")

_jinja_env: Environment | None = None


def get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=True,
            cache_size=0,
        )
    return _jinja_env


def render_template(template_name: str, **kwargs: Any) -> str:
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)


def _create_ssh_connection(config: SSHConfig) -> Any:
    """根据 host 自动选择 SSH 后端：mock 开头用 Mock，其余用 Paramiko。"""
    if not config.host or config.host.startswith("mock"):
        return MockSSHConnection(config)
    return ParamikoSSHConnection(config)


@router.get("", response_class=HTMLResponse, response_model=None)
async def manual_config_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """显示手动配置表单。"""
    device_repo = DeviceRepository(db)
    devices = device_repo.get_all()
    html = render_template(
        "manual_config.html",
        request=request,
        devices=devices,
        active_page="manual_config",
    )
    return HTMLResponse(content=html)


@router.post("", response_class=HTMLResponse, response_model=None)
async def manual_config_execute(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """执行手动配置命令并返回输出。"""
    form = await request.form()
    device_repo = DeviceRepository(db)
    audit_repo = AuditLogRepository(db)
    devices = device_repo.get_all()

    device_id_raw = form.get("device_id", "0")
    commands_text = form.get("commands", "")
    save_config = form.get("save_config") == "on"
    created_by = form.get("created_by", "web")

    try:
        device_id = int(device_id_raw)
    except (ValueError, TypeError):
        device_id = 0

    device = device_repo.get_by_id(device_id) if device_id else None

    if device is None:
        html = render_template(
            "manual_config.html",
            request=request,
            devices=devices,
            selected_device_id=device_id,
            commands_text=commands_text,
            save_config=save_config,
            error="请选择有效的设备",
            active_page="manual_config",
        )
        return HTMLResponse(content=html, status_code=400)

    # 解析命令：每行一条，忽略空行和注释行
    commands: list[str] = []
    for line in commands_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        commands.append(line)

    if not commands:
        html = render_template(
            "manual_config.html",
            request=request,
            devices=devices,
            selected_device_id=device_id,
            commands_text=commands_text,
            save_config=save_config,
            error="请输入至少一条命令",
            active_page="manual_config",
        )
        return HTMLResponse(content=html, status_code=400)

    # 创建 SSH 连接并执行命令
    encryption = EncryptionManager()
    password = encryption.decrypt(device.encrypted_password)
    ssh_config = SSHConfig(
        host=device.management_ip,
        port=device.port,
        username=device.username,
        password=password,
        timeout=30,
        auto_add_host_key=True,
    )

    results: list[dict[str, str]] = []
    connection_error: str | None = None

    try:
        connection = _create_ssh_connection(ssh_config)
        connection.connect()

        for cmd in commands:
            try:
                output = connection.send_command(cmd)
                results.append({"command": cmd, "output": output, "status": "ok"})
            except Exception as e:
                results.append({"command": cmd, "output": str(e), "status": "error"})
                break

        if save_config and results and results[-1]["status"] == "ok":
            try:
                save_output = connection.save_config()
                results.append({"command": "save force", "output": save_output, "status": "ok"})
            except Exception as e:
                results.append({"command": "save force", "output": str(e), "status": "error"})

        connection.disconnect()

    except Exception as e:
        connection_error = str(e)

    # 审计日志
    audit_repo.log(
        action="MANUAL_CONFIG",
        resource_type="DEVICE",
        resource_id=str(device_id),
        actor=created_by,
        details={
            "device_name": device.name,
            "command_count": len(commands),
            "save_config": save_config,
            "success": connection_error is None,
        },
    )

    html = render_template(
        "manual_config.html",
        request=request,
        devices=devices,
        selected_device_id=device_id,
        commands_text=commands_text,
        save_config=save_config,
        results=results,
        error=connection_error,
        active_page="manual_config",
    )
    return HTMLResponse(content=html)
