from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from minince.infrastructure.database.connection import get_db
from minince.infrastructure.drivers import get_driver
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.exceptions import ValidationError

router = APIRouter(tags=["vlan"])


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


@router.post("/api/v1/devices/{device_id}/vlan/preview")
async def api_vlan_preview(
    device_id: int,
    intent: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """预览 VLAN 配置命令（不执行）。"""
    driver = _create_driver(db, device_id)

    intent_data = dict(intent)
    intent_data.setdefault("feature", "VLAN")

    try:
        current_state = driver.get_current_state(intent_data)
        plan = driver.build_plan(intent_data, current_state)

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


@router.post("/api/v1/devices/{device_id}/vlan/deploy")
async def api_vlan_deploy(
    device_id: int,
    intent: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """下发 VLAN 配置并验证。"""
    driver = _create_driver(db, device_id)

    intent_data = dict(intent)
    intent_data.setdefault("feature", "VLAN")

    try:
        current_state = driver.get_current_state(intent_data)
        plan = driver.build_plan(intent_data, current_state)

        if not plan.changed:
            return {
                "device_id": device_id,
                "success": True,
                "changed": False,
                "message": "VLAN 配置已与期望一致，无需变更",
                "commands": [],
                "verification": {"success": True, "details": {}},
            }

        result = driver.apply_plan(plan)

        if not result.success:
            return {
                "device_id": device_id,
                "success": False,
                "changed": True,
                "message": result.error_message or "VLAN 配置下发失败",
                "commands": plan.commands,
                "command_outputs": result.command_outputs,
            }

        verify = driver.verify(intent_data)
        return {
            "device_id": device_id,
            "success": True,
            "changed": True,
            "message": "VLAN 配置下发成功",
            "commands": plan.commands,
            "command_outputs": result.command_outputs,
            "verification": {
                "success": verify.success,
                "details": verify.details,
            },
        }
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        driver.disconnect()


@router.get("/api/v1/devices/{device_id}/vlan/state/{vlan_id}")
async def api_vlan_get_state(
    device_id: int,
    vlan_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """获取设备上指定 VLAN 的当前状态。"""
    driver = _create_driver(db, device_id)

    intent_data = {"feature": "VLAN", "vlan_id": vlan_id}
    try:
        state = driver.get_current_state(intent_data)
        return {
            "device_id": device_id,
            "vlan_id": vlan_id,
            "exists": state.exists,
            "data": state.data,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        driver.disconnect()
