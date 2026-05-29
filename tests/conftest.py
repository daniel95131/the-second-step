"""
Shared pytest fixtures.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app, set_service
from domain.projection import Projection
from infrastructure.event_store import EventStore
from infrastructure.service import LockStreamService


@pytest.fixture()
def tmp_event_log(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture()
def service(tmp_event_log: Path) -> LockStreamService:
    store = EventStore(path=tmp_event_log)
    projection = Projection()
    svc = LockStreamService(event_store=store, projection=projection)
    set_service(svc)
    return svc


@pytest.fixture()
def client(service: LockStreamService) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)
