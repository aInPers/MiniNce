from __future__ import annotations

import pytest

from minince.infrastructure.repositories.device_repository import DeviceRepository
from minince.infrastructure.repositories.task_repository import TaskRepository


class TestTaskRepository:
    @pytest.fixture
    def device_id(self, test_db) -> int:
        device_repo = DeviceRepository(test_db)
        device = device_repo.create(
            name="SW-Test",
            hostname="sw-test",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        return device.id

    def test_create_task(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-001",
            task_type="VLAN_CREATE",
            device_id=device_id,
            risk_level="MEDIUM",
            original_request={"vlan_id": 100, "name": "TEST_VLAN"},
        )
        assert task.id is not None
        assert task.task_number == "TASK-001"
        assert task.status == "DRAFT"
        assert task.risk_level == "MEDIUM"
        assert task.original_request == {"vlan_id": 100, "name": "TEST_VLAN"}

    def test_get_by_id(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        created = repo.create(
            task_number="TASK-002",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.task_number == "TASK-002"

    def test_get_by_task_number(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        repo.create(
            task_number="TASK-UNIQUE",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        fetched = repo.get_by_task_number("TASK-UNIQUE")
        assert fetched is not None
        assert fetched.task_type == "VLAN_CREATE"

    def test_get_all(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        repo.create(task_number="TASK-1", task_type="VLAN_CREATE", device_id=device_id)
        repo.create(task_number="TASK-2", task_type="VLAN_DELETE", device_id=device_id)
        tasks = repo.get_all()
        assert len(tasks) == 2

    def test_get_all_with_status_filter(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task1 = repo.create(task_number="TASK-1", task_type="VLAN_CREATE", device_id=device_id)
        task2 = repo.create(task_number="TASK-2", task_type="VLAN_DELETE", device_id=device_id)
        repo.update_status(task1.id, "RUNNING")
        running = repo.get_all(status="RUNNING")
        assert len(running) == 1
        assert running[0].task_number == "TASK-1"

    def test_count_all(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        assert repo.count_all() == 0
        repo.create(task_number="TASK-1", task_type="VLAN_CREATE", device_id=device_id)
        assert repo.count_all() == 1

    def test_update_status(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-STATUS",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        updated = repo.update_status(task.id, "RUNNING")
        assert updated is not None
        assert updated.status == "RUNNING"
        assert updated.started_at is not None

    def test_update_status_to_completed(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-DONE",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        repo.update_status(task.id, "RUNNING")
        updated = repo.update_status(task.id, "SUCCEEDED")
        assert updated is not None
        assert updated.completed_at is not None

    def test_create_step(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-STEP",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        step = repo.create_step(
            task_id=task.id,
            step_name="参数验证",
            status="RUNNING",
            input_data={"vlan_id": 100},
        )
        assert step.id is not None
        assert step.step_name == "参数验证"
        assert step.status == "RUNNING"

    def test_get_steps_by_task_id(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-STEPS",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        repo.create_step(task_id=task.id, step_name="Step1", status="SUCCEEDED")
        repo.create_step(task_id=task.id, step_name="Step2", status="RUNNING")
        steps = repo.get_steps_by_task_id(task.id)
        assert len(steps) == 2

    def test_update_step(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-UPDSTEP",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        step = repo.create_step(
            task_id=task.id,
            step_name="Execute",
            status="RUNNING",
        )
        updated = repo.update_step(
            step.id,
            status="SUCCEEDED",
            output_data={"result": "success"},
        )
        assert updated is not None
        assert updated.status == "SUCCEEDED"
        assert updated.output_data == {"result": "success"}

    def test_delete_task(self, test_db, device_id) -> None:
        repo = TaskRepository(test_db)
        task = repo.create(
            task_number="TASK-DELETE",
            task_type="VLAN_CREATE",
            device_id=device_id,
        )
        assert repo.delete_by_id(task.id) is True
        assert repo.get_by_id(task.id) is None
