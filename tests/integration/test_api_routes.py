from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from minince.infrastructure.database.connection import Base, get_db
from minince.main import create_app


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    app = create_app()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


class TestHealthCheck:
    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "MiniNCE" in data["app"]

    def test_health_check_contains_version(self, client: TestClient) -> None:
        response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert data["version"] == "0.1.0"


class TestIndexPage:
    def test_index_page(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "MiniNCE" in response.text
        assert "网络自动化配置平台" in response.text

    def test_index_page_contains_stats(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "设备总数" in response.text
        assert "任务总数" in response.text

    def test_index_page_contains_quick_actions(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "添加设备" in response.text
        assert "创建VLAN任务" in response.text


class TestStatsAPI:
    def test_stats_api(self, client: TestClient) -> None:
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert "tasks" in data
        assert data["devices"]["total"] == 0

    def test_stats_api_task_counts(self, client: TestClient) -> None:
        response = client.get("/api/v1/stats")
        data = response.json()
        assert "total" in data["tasks"]
        assert "running" in data["tasks"]
        assert "succeeded" in data["tasks"]
        assert "failed" in data["tasks"]


class TestErrorHandlers:
    def test_404_not_found(self, client: TestClient) -> None:
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed(self, client: TestClient) -> None:
        response = client.post("/")
        assert response.status_code == 405
