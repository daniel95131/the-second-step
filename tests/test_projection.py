"""
Projection equivalence tests.

Verifies that incremental event application and a full rebuild from the
JSONL log yield identical state_hash values.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from domain.projection import Projection
from infrastructure.event_store import EventStore
from infrastructure.service import LockStreamService
from tests.factories import (
    compartment_registered,
    fault_cleared,
    fault_reported,
    parcel_deposited,
    parcel_picked_up,
    reservation_created,
    reservation_expired,
)
from fastapi.testclient import TestClient
from api.app import app, set_service


def _build_service(path: Path) -> tuple[LockStreamService, TestClient]:
    store = EventStore(path=path)
    projection = Projection()
    svc = LockStreamService(event_store=store, projection=projection)
    set_service(svc)
    return svc, TestClient(app)


class TestProjectionEquivalence:

    def _post_scenario(self, client: TestClient) -> list[str]:
        """Post a realistic sequence of events and return locker IDs touched."""
        locker = "L-EQUIV"
        for i in range(3):
            client.post("/events", json=compartment_registered(locker_id=locker, compartment_id=f"C{i}"))

        res1 = str(uuid.uuid4())
        res2 = str(uuid.uuid4())
        fault1 = str(uuid.uuid4())

        client.post("/events", json=reservation_created(locker_id=locker, compartment_id="C0", reservation_id=res1))
        client.post("/events", json=parcel_deposited(locker_id=locker, reservation_id=res1))
        client.post("/events", json=parcel_picked_up(locker_id=locker, reservation_id=res1))

        client.post("/events", json=reservation_created(locker_id=locker, compartment_id="C1", reservation_id=res2))
        client.post("/events", json=reservation_expired(locker_id=locker, reservation_id=res2))

        client.post("/events", json=fault_reported(locker_id=locker, compartment_id="C2", severity=3, event_id=fault1))
        client.post("/events", json=fault_cleared(locker_id=locker, compartment_id="C2", fault_event_id=fault1))

        return [locker]

    def test_incremental_and_rebuild_yield_same_hash(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"

        # --- Phase 1: incremental application ---
        svc, client = _build_service(log_path)
        lockers = self._post_scenario(client)

        incremental_hashes = {
            locker: client.get(f"/lockers/{locker}").json()["state_hash"]
            for locker in lockers
        }

        # --- Phase 2: full rebuild from JSONL ---
        store2 = EventStore(path=log_path)
        projection2 = Projection()
        svc2 = LockStreamService(event_store=store2, projection=projection2)
        svc2.rebuild_projection()
        set_service(svc2)
        client2 = TestClient(app)

        rebuilt_hashes = {
            locker: client2.get(f"/lockers/{locker}").json()["state_hash"]
            for locker in lockers
        }

        assert incremental_hashes == rebuilt_hashes

    def test_rebuild_from_empty_log_is_clean(self, tmp_path: Path) -> None:
        log_path = tmp_path / "empty.jsonl"
        log_path.touch()
        store = EventStore(path=log_path)
        projection = Projection()
        svc = LockStreamService(event_store=store, projection=projection)
        svc.rebuild_projection()
        # No lockers → nothing to assert on, just no crash
        assert svc.get_locker_summary("GHOST") is None

    def test_state_hash_changes_after_new_event(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        svc, client = _build_service(log_path)

        client.post("/events", json=compartment_registered(locker_id="L-HASH", compartment_id="C1"))
        hash1 = client.get("/lockers/L-HASH").json()["state_hash"]

        client.post("/events", json=compartment_registered(locker_id="L-HASH", compartment_id="C2"))
        hash2 = client.get("/lockers/L-HASH").json()["state_hash"]

        assert hash1 != hash2

    def test_duplicate_event_does_not_change_hash(self, tmp_path: Path) -> None:
        log_path = tmp_path / "events.jsonl"
        svc, client = _build_service(log_path)

        event = compartment_registered(locker_id="L-NOCHG", compartment_id="C1")
        client.post("/events", json=event)
        hash1 = client.get("/lockers/L-NOCHG").json()["state_hash"]

        client.post("/events", json=event)  # duplicate
        hash2 = client.get("/lockers/L-NOCHG").json()["state_hash"]

        assert hash1 == hash2
