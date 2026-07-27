from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.drivers import get_driver
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import ValidationError

router = APIRouter(tags=["ospf"])


def _create_driver(db: Session, device_id: int) -> Any:
    """加载设备并创建驱动实例。"""
    device_repo = DeviceRepository(db)
    device = device_repo.get_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    encryption = EncryptionManager()
    password = encryption.decrypt(device.encrypted_password)
    return get_driver(
        vendor=device.vendor,
        host=device.management_ip,
        port=device.port,
        username=device.username,
        password=password,
    )


@router.post("/api/v1/devices/{device_id}/ospf/preview")
async def api_ospf_preview(
    device_id: int,
    intent: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """预览 OSPF 配置命令（不执行）。"""
    driver = _create_driver(db, device_id)

    intent_data = dict(intent)
    intent_data.setdefault("feature", "OSPF")

    try:
        current_state = driver.get_current_state(intent_data)
        plan = driver.build_plan(intent_data, current_state)

        # 脱敏：如果 intent 中携带了明文 auth_secret，需要从返回的 commands 中移除
        secrets: list[str] = []
        for iface in intent_data.get("interfaces") or []:
            s = iface.get("auth_secret")
            if s:
                secrets.append(s)
        if secrets:
            redacted = list(plan.commands)
            for i, cmd in enumerate(redacted):
                for s in secrets:
                    if s and s in cmd:
                        redacted[i] = cmd.replace(s, "********")
            plan.commands = redacted

        return {
            "device_id": device_id,
            "changed": plan.changed,
            "commands": plan.commands,
            "risk_level": plan.risk_level.value,
            "warnings": plan.warnings,
            "current_state": plan.current_state,
        }
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        driver.disconnect()


@router.get("/api/v1/devices/{device_id}/ospf/state")
async def api_ospf_get_state(
    device_id: int,
    process_id: int = 1,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """获取设备当前 OSPF 状态。"""
    driver = _create_driver(db, device_id)

    intent_data = {"feature": "OSPF", "process_id": process_id}
    try:
        state = driver.get_current_state(intent_data)
        return {
            "device_id": device_id,
            "process_id": process_id,
            "exists": state.exists,
            "state": state.data,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        driver.disconnect()
