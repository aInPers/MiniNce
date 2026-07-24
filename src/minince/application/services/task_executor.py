from __future__ import annotations

from typing import Any

import structlog

from minince.domain.network.config_plan import ConfigPlan
from minince.infrastructure.drivers import get_driver
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.enums import RiskLevel, StepStatus, TaskStatus
from minince.shared.exceptions import (
    DeviceConnectionError,
    DeviceNotFoundError,
    RiskBlockedError,
    TaskExecutionError,
    TaskNotFoundError,
    TaskStateError,
)

logger = structlog.get_logger()


class TaskExecutor:
    def __init__(
        self,
        task_repo: TaskRepository,
        device_repo: DeviceRepository,
        audit_repo: AuditLogRepository,
        encryption: EncryptionManager | None = None,
    ) -> None:
        self._task_repo = task_repo
        self._device_repo = device_repo
        self._audit_repo = audit_repo
        self._encryption = encryption or EncryptionManager()

    def execute_task(self, task_id: int, force: bool = False) -> Any:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        if task.status not in (TaskStatus.DRAFT.value, TaskStatus.FAILED.value):
            if not force:
                raise TaskStateError(
                    f"Task {task_id} cannot be executed from state {task.status}",
                    current_state=task.status,
                    expected_state=TaskStatus.DRAFT.value,
                )

        self._validate_risk(task)

        try:
            self._transition(task_id, TaskStatus.VALIDATING.value)

            device = self._load_device(task.device_id)
            self._record_step(task_id, "validate_device", StepStatus.RUNNING,
                             input_data={"device_id": task.device_id})

            connection_result = self._test_connection(device)
            if not connection_result.success:
                self._record_step(task_id, "validate_device", StepStatus.FAILED,
                                  output_data=connection_result.to_dict(),
                                  error_message=connection_result.message)
                self._transition(task_id, TaskStatus.FAILED.value)
                raise DeviceConnectionError(connection_result.message)

            self._record_step(task_id, "validate_device", StepStatus.SUCCEEDED,
                              output_data=connection_result.to_dict())

            self._transition(task_id, TaskStatus.READY.value)

            driver = self._create_driver(device)
            intent = task.structured_intent or {}

            self._record_step(task_id, "get_current_state", StepStatus.RUNNING,
                             input_data={"feature": intent.get("feature")})
            current_state = driver.get_current_state(intent)
            self._record_step(task_id, "get_current_state", StepStatus.SUCCEEDED,
                             output_data=current_state.to_dict())

            self._record_step(task_id, "build_plan", StepStatus.RUNNING)
            plan = driver.build_plan(intent, current_state)
            self._record_step(task_id, "build_plan", StepStatus.SUCCEEDED,
                             output_data=plan.to_dict())

            task.generated_commands = plan.commands
            task.execution_output = {}
            self._task_repo.commit()

            self._audit_repo.log(
                action="BUILD_PLAN",
                resource_type="TASK",
                resource_id=str(task_id),
                actor="system",
                details={
                    "feature": plan.feature,
                    "changed": plan.changed,
                    "command_count": len(plan.commands),
                    "risk_level": plan.risk_level.value,
                    "warnings": plan.warnings,
                },
            )

            if not plan.changed:
                self._transition(task_id, TaskStatus.VERIFYING.value)
                self._record_step(task_id, "execute_config", StepStatus.SUCCEEDED,
                                 output_data={"message": "No changes needed"})
                self._record_step(task_id, "verify_result", StepStatus.RUNNING)
                verification = driver.verify(intent)
                self._record_step(task_id, "verify_result",
                                  StepStatus.SUCCEEDED if verification.success else StepStatus.FAILED,
                                  output_data=verification.to_dict())
                task.verification_output = verification.to_dict()
                self._task_repo.commit()
                self._transition(task_id,
                                TaskStatus.SUCCEEDED.value if verification.success else TaskStatus.FAILED.value)
                return task

            self._transition(task_id, TaskStatus.RUNNING.value)

            self._record_step(task_id, "execute_config", StepStatus.RUNNING,
                             input_data={"commands": plan.commands})
            execution_result = driver.apply_plan(plan)

            self._record_step(task_id, "execute_config",
                             StepStatus.SUCCEEDED if execution_result.success else StepStatus.FAILED,
                             output_data=execution_result.to_dict(),
                             error_message=execution_result.error_message)

            task.execution_output = execution_result.to_dict()
            self._task_repo.commit()

            if not execution_result.success:
                self._transition(task_id, TaskStatus.FAILED.value)
                raise TaskExecutionError(
                    f"Task {task_id} execution failed: {execution_result.error_message}",
                    details={"task_id": task_id, "execution_output": execution_result.to_dict()},
                )

            self._transition(task_id, TaskStatus.VERIFYING.value)

            self._record_step(task_id, "verify_result", StepStatus.RUNNING)
            verification = driver.verify(intent)

            self._record_step(task_id, "verify_result",
                             StepStatus.SUCCEEDED if verification.success else StepStatus.FAILED,
                             output_data=verification.to_dict(),
                             error_message=verification.error_message)

            task.verification_output = verification.to_dict()
            self._task_repo.commit()

            final_status = TaskStatus.SUCCEEDED.value if verification.success else TaskStatus.FAILED.value
            self._transition(task_id, final_status)

            self._audit_repo.log(
                action="EXECUTE",
                resource_type="TASK",
                resource_id=str(task_id),
                actor="system",
                details={
                    "result": final_status,
                    "verification_success": verification.success,
                },
            )

            return task

        except (DeviceNotFoundError, DeviceConnectionError, TaskExecutionError) as e:
            task = self._task_repo.get_by_id(task_id)
            if task and task.status not in TaskStatus.FAILED.value:
                self._transition(task_id, TaskStatus.FAILED.value)
            task.error_message = str(e)
            self._task_repo.commit()
            logger.error("task_execution_failed", task_id=task_id, error=str(e))
            raise
        except Exception as e:
            task = self._task_repo.get_by_id(task_id)
            if task:
                self._transition(task_id, TaskStatus.FAILED.value)
                task.error_message = str(e)
                self._task_repo.commit()
            logger.exception("task_execution_unexpected_error", task_id=task_id)
            raise TaskExecutionError(
                f"Unexpected error during task {task_id} execution: {e}",
                details={"task_id": task_id},
            )

    def preview_task(self, task_id: int) -> ConfigPlan:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        device = self._load_device(task.device_id)
        driver = self._create_driver(device)
        intent = task.structured_intent or {}

        current_state = driver.get_current_state(intent)
        plan = driver.build_plan(intent, current_state)

        task.generated_commands = plan.commands
        self._task_repo.commit()

        self._audit_repo.log(
            action="PREVIEW",
            resource_type="TASK",
            resource_id=str(task_id),
            actor="system",
            details={
                "feature": plan.feature,
                "command_count": len(plan.commands),
                "changed": plan.changed,
            },
        )

        return plan

    def _validate_risk(self, task: Any) -> None:
        risk = RiskLevel(task.risk_level)
        if risk.requires_confirmation and not task.created_by.startswith("admin_"):
            raise RiskBlockedError(
                f"Task {task.id} requires user confirmation due to {risk.value} risk level",
                risk_level=risk.value,
            )

    def _load_device(self, device_id: int) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)
        return device

    def _test_connection(self, device: Any) -> Any:
        driver = self._create_driver(device)
        return driver.test_connection()

    def _create_driver(self, device: Any) -> Any:
        password = self._encryption.decrypt(device.encrypted_password)
        return get_driver(
            vendor=device.vendor,
            host=device.management_ip,
            port=device.port,
            username=device.username,
            password=password,
        )

    def _transition(self, task_id: int, new_status: str) -> None:
        self._task_repo.update_status(task_id, new_status)
        self._audit_repo.log(
            action="TRANSITION",
            resource_type="TASK",
            resource_id=str(task_id),
            actor="system",
            details={"to": new_status},
        )

    def _record_step(
        self,
        task_id: int,
        step_name: str,
        status: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        step = self._task_repo.create_step(
            task_id=task_id,
            step_name=step_name,
            status=status,
            input_data=input_data,
        )
        if output_data is not None or error_message is not None:
            self._task_repo.update_step(
                step_id=step.id,
                status=status,
                output_data=output_data,
                error_message=error_message,
            )
