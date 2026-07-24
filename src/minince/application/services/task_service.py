from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.shared.enums import RiskLevel, TaskStatus
from minince.shared.exceptions import DeviceNotFoundError, TaskStateError, ValidationError


class TaskService:
    def __init__(
        self,
        task_repo: TaskRepository,
        device_repo: DeviceRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        self._task_repo = task_repo
        self._device_repo = device_repo
        self._audit_repo = audit_repo

    @staticmethod
    def _generate_task_number() -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_hex = secrets.token_hex(3)
        return f"TASK-{timestamp}-{random_hex.upper()}"

    def create_vlan_task(
        self,
        device_id: int,
        operation: str,
        vlan_id: int,
        name: str | None = None,
        description: str | None = None,
        created_by: str = "web",
    ) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        if operation == "delete":
            risk_level = RiskLevel.HIGH.value
        elif operation == "update":
            risk_level = RiskLevel.MEDIUM.value
        else:
            risk_level = RiskLevel.LOW.value

        task_number = self._generate_task_number()
        task_type = f"VLAN_{operation.upper()}"

        original_request = {
            "operation": operation,
            "vlan_id": vlan_id,
            "name": name,
            "description": description,
        }

        structured_intent = {
            "feature": "VLAN",
            "operation": operation,
            "vlan_id": vlan_id,
            "name": name,
            "description": description,
        }

        task = self._task_repo.create(
            task_number=task_number,
            task_type=task_type,
            device_id=device_id,
            risk_level=risk_level,
            original_request=original_request,
            created_by=created_by,
        )
        task.structured_intent = structured_intent
        self._task_repo.commit()

        self._audit_repo.log(
            action="CREATE",
            resource_type="TASK",
            resource_id=str(task.id),
            actor=created_by,
            details={"task_type": task_type, "device_id": device_id},
        )

        return task

    def create_interface_task(
        self,
        device_id: int,
        interface_name: str,
        description: str | None = None,
        admin_up: bool | None = None,
        link_type: str | None = None,
        access_vlan: int | None = None,
        trunk_allowed_vlans: list[int] | None = None,
        created_by: str = "web",
    ) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)

        if link_type == "access" and trunk_allowed_vlans:
            raise ValidationError("Access interface cannot have trunk allowed VLANs")
        if link_type == "trunk" and access_vlan is not None:
            raise ValidationError("Trunk interface cannot have access VLAN")

        risk_level = RiskLevel.MEDIUM.value
        if admin_up is False:
            risk_level = RiskLevel.HIGH.value

        task_number = self._generate_task_number()

        original_request = {
            "interface_name": interface_name,
            "description": description,
            "admin_up": admin_up,
            "link_type": link_type,
            "access_vlan": access_vlan,
            "trunk_allowed_vlans": trunk_allowed_vlans,
        }

        structured_intent = {
            "feature": "INTERFACE",
            "interface_name": interface_name,
            "description": description,
            "admin_up": admin_up,
            "link_type": link_type,
            "access_vlan": access_vlan,
            "trunk_allowed_vlans": trunk_allowed_vlans,
        }

        task = self._task_repo.create(
            task_number=task_number,
            task_type="INTERFACE_CONFIG",
            device_id=device_id,
            risk_level=risk_level,
            original_request=original_request,
            created_by=created_by,
        )
        task.structured_intent = structured_intent
        self._task_repo.commit()

        self._audit_repo.log(
            action="CREATE",
            resource_type="TASK",
            resource_id=str(task.id),
            actor=created_by,
            details={"task_type": "INTERFACE_CONFIG", "device_id": device_id},
        )

        return task

    def preview_task(self, task_id: int) -> Any:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            raise DeviceNotFoundError(task_id)

        plan = self._build_preview_plan(task)
        task.generated_commands = plan.commands
        self._task_repo.commit()

        self._audit_repo.log(
            action="PREVIEW",
            resource_type="TASK",
            resource_id=str(task_id),
            actor="web",
            details={"command_count": len(plan.commands)},
        )

        return task

    def _build_preview_plan(self, task: Any) -> Any:
        from minince.domain.network.config_plan import ConfigPlan

        intent = task.structured_intent or {}
        feature = intent.get("feature", "UNKNOWN")

        commands: list[str] = []
        verify_commands: list[str] = []
        warnings: list[str] = []

        if feature == "VLAN":
            vlan_id = intent.get("vlan_id")
            operation = intent.get("operation", "create")
            vlan_name = intent.get("name", "")
            vlan_desc = intent.get("description", "")

            if operation == "create":
                commands.append(f"vlan {vlan_id}")
                if vlan_name:
                    commands.append(f" name {vlan_name}")
                if vlan_desc:
                    commands.append(f" description {vlan_desc}")
                commands.append("quit")
                verify_commands.append(f"display vlan {vlan_id}")
            elif operation == "update":
                commands.append(f"vlan {vlan_id}")
                if vlan_name:
                    commands.append(f" name {vlan_name}")
                if vlan_desc:
                    commands.append(f" description {vlan_desc}")
                commands.append("quit")
                verify_commands.append(f"display vlan {vlan_id}")
            elif operation == "delete":
                commands.append(f"undo vlan {vlan_id}")
                warnings.append(f"Deleting VLAN {vlan_id} will remove all interfaces from this VLAN")
                verify_commands.append(f"display vlan {vlan_id}")

        elif feature == "INTERFACE":
            ifname = intent.get("interface_name", "")
            commands.append(f"interface {ifname}")
            desc = intent.get("description")
            if desc:
                commands.append(f" description {desc}")
            admin_up = intent.get("admin_up")
            if admin_up is not None:
                commands.append(" undo shutdown" if admin_up else " shutdown")
            link_type = intent.get("link_type")
            if link_type == "access":
                access_vlan = intent.get("access_vlan")
                if access_vlan:
                    commands.append(f" port default vlan {access_vlan}")
            elif link_type == "trunk":
                commands.append(" port link-type trunk")
                trunk_vlans = intent.get("trunk_allowed_vlans")
                if trunk_vlans:
                    vlan_str = ",".join(str(v) for v in trunk_vlans)
                    commands.append(f" port trunk allow-pass vlan {vlan_str}")
            commands.append("quit")
            verify_commands.append(f"display current-configuration interface {ifname}")

        return ConfigPlan(
            device_id=task.device_id,
            feature=feature,
            intent=intent,
            current_state={},
            commands=commands,
            verify_commands=verify_commands,
            changed=True,
            risk_level=RiskLevel(task.risk_level),
            warnings=warnings,
        )

    def get_task(self, task_id: int) -> Any:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            from minince.shared.exceptions import TaskNotFoundError
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> tuple[list[Any], int]:
        tasks = self._task_repo.get_all(skip=skip, limit=limit, status=status)
        total = self._task_repo.count_all(status=status)
        return tasks, total

    def get_task_steps(self, task_id: int) -> list[Any]:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            from minince.shared.exceptions import TaskNotFoundError
            raise TaskNotFoundError(task_id)
        return self._task_repo.get_steps_by_task_id(task_id)

    def transition_status(self, task_id: int, new_status: str) -> Any:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            from minince.shared.exceptions import TaskNotFoundError
            raise TaskNotFoundError(task_id)

        valid_transitions = {
            TaskStatus.DRAFT.value: [TaskStatus.VALIDATING.value, TaskStatus.FAILED.value],
            TaskStatus.VALIDATING.value: [TaskStatus.READY.value, TaskStatus.FAILED.value],
            TaskStatus.READY.value: [TaskStatus.RUNNING.value, TaskStatus.FAILED.value],
            TaskStatus.RUNNING.value: [TaskStatus.VERIFYING.value, TaskStatus.FAILED.value, TaskStatus.PARTIAL.value],
            TaskStatus.VERIFYING.value: [TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.PARTIAL.value],
        }

        allowed = valid_transitions.get(task.status, [])
        if new_status not in allowed:
            raise TaskStateError(
                f"Cannot transition from {task.status} to {new_status}",
                current_state=task.status,
                expected_state=new_status,
            )

        updated = self._task_repo.update_status(task_id, new_status)

        self._audit_repo.log(
            action="TRANSITION",
            resource_type="TASK",
            resource_id=str(task_id),
            actor="system",
            details={"from": task.status, "to": new_status},
        )

        return updated
