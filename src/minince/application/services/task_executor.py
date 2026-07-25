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

# 允许执行的任务状态：仅 DRAFT 和 FAILED 可启动执行
_ALLOWED_EXECUTION_STATES = {TaskStatus.DRAFT.value, TaskStatus.FAILED.value}


class TaskExecutor:
    """任务执行器。

    安全修复说明：
    - #4: 移除 admin_ 前缀绕过，高风险任务必须显式 confirmed=True
    - #5: force 不再完全跳过状态机，仅允许从 DRAFT/FAILED 重试
    - #6: 原子抢占机制，通过 version 字段防止并发执行同一任务
    - #7: preview_task 添加 try/finally 释放 SSH 连接
    - #8: 测试连接与执行复用同一 driver，避免连接泄漏
    - #9: 修复 not in 字符串判断 bug
    - #13: 步骤记录改为生命周期更新而非每次新建
    """

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

    def execute_task(self, task_id: int, force: bool = False, confirmed: bool = False) -> Any:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        # #5: force 不再完全跳过状态机，仅允许从 DRAFT/FAILED 重试
        if task.status not in _ALLOWED_EXECUTION_STATES:
            if not force:
                raise TaskStateError(
                    f"Task {task_id} cannot be executed from state {task.status}",
                    current_state=task.status,
                    expected_state=TaskStatus.DRAFT.value,
                )
            # force=True 时仅允许从 DRAFT/FAILED 重试，不允许重执行 RUNNING/VERIFYING/SUCCEEDED
            raise TaskStateError(
                f"Task {task_id} is in state {task.status}, force retry only allowed from "
                f"DRAFT or FAILED states",
                current_state=task.status,
                expected_state="DRAFT or FAILED",
            )

        # #4: 移除 admin_ 前缀绕过，高风险任务必须显式确认
        self._validate_risk(task, confirmed=confirmed)

        # #6: 原子抢占任务，防止并发执行
        acquired, token = self._task_repo.try_acquire_task(
            task_id=task_id,
            expected_status=task.status,
            new_status=TaskStatus.VALIDATING.value,
        )
        if not acquired:
            raise TaskStateError(
                f"Task {task_id} was acquired by another executor or state changed",
                current_state=task.status,
                expected_state="DRAFT or FAILED",
            )

        driver = None
        try:
            device = self._load_device(task.device_id)

            # #8: 复用同一 driver 进行连接测试和执行，避免创建多个 SSH 会话
            driver = self._create_driver(device)

            step_id = self._start_step(task_id, "validate_device",
                                        input_data={"device_id": task.device_id})

            # 使用复用的 driver 测试连接
            connection_result = driver.test_connection()
            if not connection_result.success:
                self._finish_step(step_id, StepStatus.FAILED.value,
                                  output_data=connection_result.to_dict(),
                                  error_message=connection_result.message)
                self._transition(task_id, TaskStatus.FAILED.value)
                raise DeviceConnectionError(connection_result.message)

            self._finish_step(step_id, StepStatus.SUCCEEDED.value,
                              output_data=connection_result.to_dict())

            self._transition(task_id, TaskStatus.READY.value)

            intent = task.structured_intent or {}

            step_id = self._start_step(task_id, "get_current_state",
                                        input_data={"feature": intent.get("feature")})
            current_state = driver.get_current_state(intent)
            self._finish_step(step_id, StepStatus.SUCCEEDED.value,
                              output_data=current_state.to_dict())

            step_id = self._start_step(task_id, "build_plan")
            plan = driver.build_plan(intent, current_state)
            self._finish_step(step_id, StepStatus.SUCCEEDED.value,
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
                step_id = self._start_step(task_id, "execute_config")
                self._finish_step(step_id, StepStatus.SUCCEEDED.value,
                                  output_data={"message": "No changes needed"})
                step_id = self._start_step(task_id, "verify_result")
                verification = driver.verify(intent)
                self._finish_step(step_id,
                                  StepStatus.SUCCEEDED.value if verification.success else StepStatus.FAILED.value,
                                  output_data=verification.to_dict())
                task.verification_output = verification.to_dict()
                self._task_repo.commit()
                self._transition(task_id,
                                TaskStatus.SUCCEEDED.value if verification.success else TaskStatus.FAILED.value)
                return task

            self._transition(task_id, TaskStatus.RUNNING.value)

            step_id = self._start_step(task_id, "execute_config",
                                        input_data={"commands": plan.commands})
            execution_result = driver.apply_plan(plan)

            self._finish_step(step_id,
                             StepStatus.SUCCEEDED.value if execution_result.success else StepStatus.FAILED.value,
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

            step_id = self._start_step(task_id, "verify_result")
            verification = driver.verify(intent)

            self._finish_step(step_id,
                             StepStatus.SUCCEEDED.value if verification.success else StepStatus.FAILED.value,
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
            # #9: 修复 not in 字符串判断 bug，改为 != 比较
            if task and task.status != TaskStatus.FAILED.value:
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
        finally:
            # #7/#8: 确保在任务完成后断开 SSH 连接，释放设备会话
            if driver is not None:
                driver.disconnect()

    def preview_task(self, task_id: int) -> ConfigPlan:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        device = self._load_device(task.device_id)
        driver = self._create_driver(device)
        intent = task.structured_intent or {}

        # #7: 添加 try/finally 释放 SSH 连接，避免预览泄漏
        try:
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
        finally:
            driver.disconnect()

    def _validate_risk(self, task: Any, confirmed: bool = False) -> None:
        """验证任务风险等级。

        #4: 移除 admin_ 前缀绕过，高风险任务必须显式 confirmed=True。
        身份和权限不应通过可伪造的字符串前缀判断。
        """
        risk = RiskLevel(task.risk_level)
        if risk.requires_confirmation and not confirmed:
            raise RiskBlockedError(
                f"Task {task.id} requires user confirmation due to {risk.value} risk level",
                risk_level=risk.value,
            )

    def _load_device(self, device_id: int) -> Any:
        device = self._device_repo.get_by_id(device_id)
        if device is None:
            raise DeviceNotFoundError(device_id)
        return device

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

    def _start_step(
        self,
        task_id: int,
        step_name: str,
        input_data: dict[str, Any] | None = None,
    ) -> int:
        """启动步骤，#13: 复用未终结的同名步骤而非新建。

        若存在同名的 PENDING/RUNNING 步骤，则复用之；
        否则创建新步骤并返回其 ID。
        """
        existing = self._task_repo.get_active_step_by_name(task_id, step_name)
        if existing is not None:
            # 复用已有步骤，更新状态为 RUNNING
            updated = self._task_repo.update_step(
                step_id=existing.id,
                status=StepStatus.RUNNING.value,
                input_data=input_data,
            )
            return updated.id if updated else existing.id

        step = self._task_repo.create_step(
            task_id=task_id,
            step_name=step_name,
            status=StepStatus.RUNNING.value,
            input_data=input_data,
        )
        return step.id

    def _finish_step(
        self,
        step_id: int,
        status: str,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """完成步骤，更新状态而非创建新记录。"""
        self._task_repo.update_step(
            step_id=step_id,
            status=status,
            output_data=output_data,
            error_message=error_message,
        )
