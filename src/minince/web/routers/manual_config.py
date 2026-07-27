from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from minince.infrastructure.database.connection import SessionLocal
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.infrastructure.ssh.base import SSHConfig

router = APIRouter(prefix="/manual-config", tags=["manual-config"])

logger = logging.getLogger(__name__)

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


@router.get("", response_class=HTMLResponse, response_model=None)
async def manual_config_page(request: Request) -> HTMLResponse:
    """显示交互式 SSH 终端页面。"""
    db = SessionLocal()
    try:
        device_repo = DeviceRepository(db)
        devices = device_repo.get_all()
    finally:
        db.close()

    html = render_template(
        "manual_config.html",
        request=request,
        devices=devices,
        active_page="manual_config",
    )
    return HTMLResponse(content=html)


@router.websocket("/ws/{device_id}")
async def terminal_websocket(websocket: WebSocket, device_id: int) -> None:
    """交互式 SSH 终端 WebSocket 端点。

    建立 paramiko SSH 连接，调用 invoke_shell() 获取原始交互式 shell 通道，
    在 SSH shell 与 WebSocket 客户端之间双向转发字节流，不做命令解析、
    分页处理或回显过滤，让用户像直接连接 SSH 客户端一样操作设备。
    """
    await websocket.accept()

    db = SessionLocal()
    audit_repo = AuditLogRepository(db)
    device_repo = DeviceRepository(db)

    device = device_repo.get_by_id(device_id)
    if device is None:
        await _safe_send_text(websocket, f"\r\n错误: 设备 ID {device_id} 不存在\r\n")
        await _safe_close(websocket)
        db.close()
        return

    if device.management_ip.startswith("mock:"):
        await _safe_send_text(
            websocket,
            f"\r\n错误: Mock 设备 ({device.management_ip}) 不支持交互式终端\r\n"
            f"请在设备管理中添加真实 IP 设备后再使用本功能。\r\n",
        )
        await _safe_close(websocket)
        db.close()
        return

    encryption = EncryptionManager()
    try:
        password = encryption.decrypt(device.encrypted_password)
    except Exception as e:
        await _safe_send_text(websocket, f"\r\n密码解密失败: {e}\r\n")
        await _safe_close(websocket)
        db.close()
        return

    ssh_config = SSHConfig(
        host=device.management_ip,
        port=device.port,
        username=device.username,
        password=password,
        timeout=30,
        auto_add_host_key=True,
    )

    try:
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=ssh_config.host,
            port=ssh_config.port,
            username=ssh_config.username,
            password=ssh_config.password,
            timeout=ssh_config.timeout,
            banner_timeout=ssh_config.banner_timeout,
            auth_timeout=ssh_config.auth_timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        # 原始交互式 shell，不做 screen-length 0 之类的预处理
        shell = client.invoke_shell(
            term="vt100",
            width=200,
            height=50,
        )
    except Exception as e:
        await _safe_send_text(websocket, f"\r\nSSH 连接失败: {e}\r\n")
        await _safe_close(websocket)
        db.close()
        return

    # 审计日志：会话开始
    try:
        audit_repo.log(
            action="INTERACTIVE_SESSION_START",
            resource_type="DEVICE",
            resource_id=str(device_id),
            actor="web",
            details={
                "device_name": device.name,
                "host": device.management_ip,
                "port": device.port,
            },
        )
    except Exception as e:
        logger.warning("记录会话开始审计日志失败: %s", e)

    stop_event = asyncio.Event()

    async def ssh_to_ws() -> None:
        """从 SSH shell 读取输出转发到 WebSocket。"""
        try:
            while not stop_event.is_set():
                if shell.recv_ready():
                    data = await asyncio.to_thread(shell.recv, 4096)
                    if not data:
                        break
                    await websocket.send_bytes(data)
                elif shell.exit_status_ready() and not shell.recv_ready():
                    # shell 已关闭且无残留数据
                    break
                else:
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.debug("SSH→WS 任务结束: %s", e)

    async def ws_to_ssh() -> None:
        """从 WebSocket 接收输入转发到 SSH shell。"""
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await asyncio.to_thread(shell.send, msg["bytes"])
                elif msg.get("text") is not None:
                    await asyncio.to_thread(
                        shell.send, msg["text"].encode("utf-8")
                    )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("WS→SSH 任务结束: %s", e)
        finally:
            stop_event.set()

    task_in = asyncio.create_task(ws_to_ssh())
    task_out = asyncio.create_task(ssh_to_ws())

    try:
        await asyncio.wait({task_in, task_out}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop_event.set()
        for task in (task_in, task_out):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        try:
            shell.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass

        # 审计日志：会话结束
        try:
            audit_repo.log(
                action="INTERACTIVE_SESSION_END",
                resource_type="DEVICE",
                resource_id=str(device_id),
                actor="web",
                details={"device_name": device.name},
            )
        except Exception as e:
            logger.warning("记录会话结束审计日志失败: %s", e)

        await _safe_close(websocket)
        db.close()


async def _safe_send_text(ws: WebSocket, text: str) -> None:
    try:
        await ws.send_text(text)
    except Exception:
        pass


async def _safe_close(ws: WebSocket) -> None:
    try:
        await ws.close()
    except Exception:
        pass
