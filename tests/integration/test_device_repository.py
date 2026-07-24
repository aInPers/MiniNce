from __future__ import annotations

import pytest

from minince.infrastructure.repositories.device_repository import DeviceRepository


class TestDeviceRepository:
    def test_create_device(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        device = repo.create(
            name="SW-Core-01",
            hostname="switch-core-01",
            management_ip="192.168.1.1",
            encrypted_password="encrypted-pass",
            vendor="HUAWEI",
            username="admin",
        )
        assert device.id is not None
        assert device.name == "SW-Core-01"
        assert device.management_ip == "192.168.1.1"
        assert device.status == "INACTIVE"
        assert device.created_at is not None

    def test_get_by_id(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        created = repo.create(
            name="SW-01",
            hostname="sw-01",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.name == "SW-01"

    def test_get_by_id_not_found(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        result = repo.get_by_id(9999)
        assert result is None

    def test_get_by_name(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        repo.create(
            name="SW-Unique",
            hostname="sw-unique",
            management_ip="10.0.0.2",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        fetched = repo.get_by_name("SW-Unique")
        assert fetched is not None
        assert fetched.management_ip == "10.0.0.2"

    def test_get_all(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        repo.create(name="SW-1", hostname="sw-1", management_ip="10.0.0.1",
                    encrypted_password="enc", vendor="HUAWEI", username="admin")
        repo.create(name="SW-2", hostname="sw-2", management_ip="10.0.0.2",
                    encrypted_password="enc", vendor="HUAWEI", username="admin")
        devices = repo.get_all()
        assert len(devices) == 2

    def test_count_all(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        assert repo.count_all() == 0
        repo.create(name="SW-1", hostname="sw-1", management_ip="10.0.0.1",
                    encrypted_password="enc", vendor="HUAWEI", username="admin")
        assert repo.count_all() == 1

    def test_update_device(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        device = repo.create(
            name="SW-Update",
            hostname="sw-update",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        updated = repo.update(device.id, description="Updated description")
        assert updated is not None
        assert updated.description == "Updated description"

    def test_update_status(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        device = repo.create(
            name="SW-Status",
            hostname="sw-status",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        updated = repo.update_status(device.id, "ACTIVE")
        assert updated is not None
        assert updated.status == "ACTIVE"

    def test_delete_by_id(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        device = repo.create(
            name="SW-Delete",
            hostname="sw-delete",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        assert repo.delete_by_id(device.id) is True
        assert repo.get_by_id(device.id) is None

    def test_delete_not_found(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        assert repo.delete_by_id(9999) is False

    def test_update_last_connected(self, test_db) -> None:
        repo = DeviceRepository(test_db)
        device = repo.create(
            name="SW-Last",
            hostname="sw-last",
            management_ip="10.0.0.1",
            encrypted_password="enc",
            vendor="HUAWEI",
            username="admin",
        )
        updated = repo.update_last_connected(device.id)
        assert updated is not None
        assert updated.last_connected_at is not None
