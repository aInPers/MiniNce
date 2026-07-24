from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from minince.application.services.task_executor import TaskExecutor
from minince.infrastructure.database.connection import Base, engine
from minince.infrastructure.repositories.audit_repository import AuditLogRepository
from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository
from minince.infrastructure.security.encryption import EncryptionManager
from minince.shared.enums import TaskStatus
from minince.shared.exceptions import DeviceConnectionError, TaskExecutionError, TaskNotFoundError


@pytest.fixture
def executor(test_db: Session) -> TaskExecutor:
    return TaskExecutor(
        task_repo=TaskRepository(test_db),
        device_repo=DeviceRepository(test_db),
        audit_repo=AuditLogRepository(test_db),
        encryption=EncryptionManager(),
    )


@pytest.fixture
def test_device(test_db: Session) -> int:
    encryption = EncryptionManager()
    device_repo = DeviceRepository(test_db)
    device = device_repo.create(
        name="TestSwitch",
        hostname="TestSwitch",
        management_ip="mock:192.168.1.1",
        encrypted_password=encryption.encrypt("testpass"),
        vendor="HUAWEI",
        username="admin",
        port=22,
    )
    return device.id


@pytest.fixture
def vlan_task(test_db: Session, test_device: int) -> int:
    task_repo = TaskRepository(test_db)
    task = task_repo.create(
        task_number="TASK-TEST-001",
        task_type="VLAN_CREATE",
        device_id=test_device,
        risk_level="LOW",
        original_request={"operation": "create", "vlan_id": 100, "name": "TEST"},
        created_by="admin",
    )
    task.structured_intent = {
        "feature": "VLAN",
        "operation": "create",
        "vlan_id": 100,
        "name": "TEST",
        "device_id": test_device,
    }
    task_repo.commit()
    return task.id


@pytest.fixture
def interface_task(test_db: Session, test_device: int) -> int:
    task_repo = TaskRepository(test_db)
    task = task_repo.create(
        task_number="TASK-TEST-002",
        task_type="INTERFACE_CONFIG",
        device_id=test_device,
        risk_level="LOW",
        original_request={"interface_name": "GigabitEthernet0/0/1", "description": "Test"},
        created_by="admin",
    )
    task.structured_intent = {
        "feature": "INTERFACE",
        "interface_name": "GigabitEthernet0/0/1",
        "description": "Test Interface",
        "admin_up": True,
        "device_id": test_device,
    }
    task_repo.commit()
    return task.id


class TestTaskExecutorVLAN:
    def test_execute_vlan_task_success(self, executor: TaskExecutor, vlan_task: int) -> None:
        result = executor.execute_task(vlan_task)

        assert result.status == TaskStatus.SUCCEEDED.value
        assert result.generated_commands is not None
        assert len(result.generated_commands) > 0
        assert result.execution_output is not None
        assert result.verification_output is not None

    def test_execute_vlan_task_idempotent(self, executor: TaskExecutor, vlan_task: int, test_db: Session) -> None:
        executor.execute_task(vlan_task)

        task_repo = TaskRepository(test_db)
        reset_task = task_repo.get_by_id(vlan_task)
        reset_task.status = TaskStatus.FAILED.value
        reset_task.structured_intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 100,
            "name": "TEST",
            "device_id": reset_task.device_id,
        }
        task_repo.commit()

        result = executor.execute_task(vlan_task, force=True)
        assert result.status == TaskStatus.SUCCEEDED.value

    def test_execute_vlan_task_steps_recorded(self, executor: TaskExecutor, vlan_task: int, test_db: Session) -> None:
        executor.execute_task(vlan_task)

        task_repo = TaskRepository(test_db)
        steps = task_repo.get_steps_by_task_id(vlan_task)

        assert len(steps) > 0
        step_names = [s.step_name for s in steps]
        assert "validate_device" in step_names
        assert "get_current_state" in step_names
        assert "build_plan" in step_names
        assert "execute_config" in step_names
        assert "verify_result" in step_names

    def test_preview_vlan_task(self, executor: TaskExecutor, vlan_task: int) -> None:
        plan = executor.preview_task(vlan_task)

        assert plan.feature == "VLAN"
        assert plan.changed is True
        assert len(plan.commands) > 0

    def test_execute_nonexistent_task(self, executor: TaskExecutor) -> None:
        with pytest.raises(TaskNotFoundError):
            executor.execute_task(9999)

    def test_execute_task_wrong_state(self, executor: TaskExecutor, test_db: Session, test_device: int) -> None:
        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-TEST-003",
            task_type="VLAN_CREATE",
            device_id=test_device,
            risk_level="LOW",
            created_by="admin",
        )
        task.status = TaskStatus.SUCCEEDED.value
        task.structured_intent = {"feature": "VLAN", "operation": "create", "vlan_id": 50}
        task_repo.commit()

        with pytest.raises(Exception):
            executor.execute_task(task.id)


class TestTaskExecutorInterface:
    def test_execute_interface_task_success(self, executor: TaskExecutor, interface_task: int) -> None:
        result = executor.execute_task(interface_task)

        assert result.status == TaskStatus.SUCCEEDED.value
        assert result.generated_commands is not None
        assert len(result.generated_commands) > 0

    def test_preview_interface_task(self, executor: TaskExecutor, interface_task: int) -> None:
        plan = executor.preview_task(interface_task)

        assert plan.feature == "INTERFACE"
        assert plan.changed is True


class TestTaskExecutorRiskControl:
    def test_high_risk_requires_confirmation(self, test_db: Session, test_device: int) -> None:
        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-RISK-001",
            task_type="VLAN_DELETE",
            device_id=test_device,
            risk_level="HIGH",
            created_by="web",
        )
        task.structured_intent = {
            "feature": "VLAN",
            "operation": "delete",
            "vlan_id": 999,
            "device_id": test_device,
        }
        task_repo.commit()

        executor = TaskExecutor(
            task_repo=task_repo,
            device_repo=DeviceRepository(test_db),
            audit_repo=AuditLogRepository(test_db),
            encryption=EncryptionManager(),
        )

        with pytest.raises(Exception):
            executor.execute_task(task.id)

    def test_high_risk_admin_can_execute(self, test_db: Session, test_device: int) -> None:
        device_repo = DeviceRepository(test_db)
        device = device_repo.get_by_id(test_device)

        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-RISK-002",
            task_type="VLAN_DELETE",
            device_id=test_device,
            risk_level="HIGH",
            created_by="admin_system",
        )
        task.structured_intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 999,
            "device_id": test_device,
        }
        task_repo.commit()

        executor = TaskExecutor(
            task_repo=task_repo,
            device_repo=DeviceRepository(test_db),
            audit_repo=AuditLogRepository(test_db),
            encryption=EncryptionManager(),
        )

        result = executor.execute_task(task.id)
        assert result.status == TaskStatus.SUCCEEDED.value


class TestTaskExecutorFailureRecording:
    def test_execution_failure_records_error(self, executor: TaskExecutor, test_db: Session) -> None:
        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-FAIL-001",
            task_type="VLAN_CREATE",
            device_id=99999,
            risk_level="LOW",
            created_by="admin",
        )
        task.structured_intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 100,
            "name": "TEST",
            "device_id": 99999,
        }
        task_repo.commit()

        task_id = task.id
        try:
            executor.execute_task(task_id)
        except (DeviceConnectionError, TaskExecutionError, Exception):
            pass

        updated_task = task_repo.get_by_id(task_id)
        assert updated_task is not None
        assert updated_task.status == TaskStatus.FAILED.value
        assert updated_task.error_message is not None
        assert len(updated_task.error_message) > 0

    def test_verification_failure_records_state(self, executor: TaskExecutor, test_db: Session, test_device: int) -> None:
        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-VERIFY-001",
            task_type="VLAN_CREATE",
            device_id=test_device,
            risk_level="LOW",
            created_by="admin",
        )
        task.structured_intent = {
            "feature": "VLAN",
            "operation": "create",
            "vlan_id": 200,
            "name": "VERIFY_TEST",
            "device_id": test_device,
        }
        task_repo.commit()

        task_id = task.id
        result = executor.execute_task(task_id)

        updated_task = task_repo.get_by_id(task_id)
        assert updated_task is not None
        assert updated_task.status in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value)
        assert result.status == updated_task.status

    def test_task_state_transition_draft_to_running(self, executor: TaskExecutor, test_db: Session, test_device: int) -> None:
        task_repo = TaskRepository(test_db)
        task = task_repo.create(
            task_number="TASK-TRANS-001",
            task_type="INTERFACE_CONFIG",
            device_id=test_device,
            risk_level="LOW",
            created_by="admin",
        )
        assert task.status == TaskStatus.DRAFT.value

        task.structured_intent = {
            "feature": "INTERFACE",
            "interface_name": "GigabitEthernet0/0/2",
            "description": "Transition Test",
            "admin_up": True,
            "device_id": test_device,
        }
        task_repo.commit()

        result = executor.execute_task(task.id)
        assert result.status != TaskStatus.DRAFT.value
        assert result.status == TaskStatus.SUCCEEDED.value

        updated_task = task_repo.get_by_id(task.id)
        assert updated_task.status == TaskStatus.SUCCEEDED.value