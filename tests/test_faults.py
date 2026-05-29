"""
Tests for fault reporting, degradation threshold, and fault clearing.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.factories import (
    compartment_registered,
    fault_cleared,
    fault_reported,
    reservation_created,
)


class TestFaultDegradation:
    LOCKER = "L-FAULT"
    COMP = "C1"

    def _setup(self, client: TestClient) -> None:
        client.post("/events", json=compartment_registered(locker_id=self.LOCKER, compartment_id=self.COMP))

    def test_low_severity_fault_does_not_degrade(self, client: TestClient) -> None:
        self._setup(client)
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=2))
        status = client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()
        assert status["degraded"] is False

    def test_high_severity_fault_degrades_compartment(self, client: TestClient) -> None:
        self._setup(client)
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=3))
        status = client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()
        assert status["degraded"] is True

    def test_degraded_compartment_cannot_accept_reservation(self, client: TestClient) -> None:
        self._setup(client)
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=3))
        resp = client.post("/events", json=reservation_created(locker_id=self.LOCKER, compartment_id=self.COMP))
        assert resp.status_code == 409

    def test_clearing_fault_removes_degradation(self, client: TestClient) -> None:
        self._setup(client)
        fault_eid = str(uuid.uuid4())
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=3, event_id=fault_eid))
        assert client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()["degraded"] is True

        client.post("/events", json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault_eid))
        assert client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()["degraded"] is False

    def test_clearing_fault_allows_new_reservation(self, client: TestClient) -> None:
        self._setup(client)
        fault_eid = str(uuid.uuid4())
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=3, event_id=fault_eid))
        client.post("/events", json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault_eid))
        resp = client.post("/events", json=reservation_created(locker_id=self.LOCKER, compartment_id=self.COMP))
        assert resp.status_code == 202

    def test_locker_summary_counts_degraded(self, client: TestClient) -> None:
        locker = "L-DEG-COUNT"
        for i in range(3):
            client.post("/events", json=compartment_registered(locker_id=locker, compartment_id=f"C{i}"))
        # Degrade only C0
        client.post("/events", json=fault_reported(locker_id=locker, compartment_id="C0", severity=5))
        summary = client.get(f"/lockers/{locker}").json()
        assert summary["degraded_compartments"] == 1

    def test_multiple_faults_all_must_be_cleared(self, client: TestClient) -> None:
        self._setup(client)
        fault1 = str(uuid.uuid4())
        fault2 = str(uuid.uuid4())
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=3, event_id=fault1))
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=4, event_id=fault2))
        # Clear only fault1 – still degraded because of fault2
        client.post("/events", json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault1))
        assert client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()["degraded"] is True
        # Clear fault2 – now clean
        client.post("/events", json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault2))
        assert client.get(f"/lockers/{self.LOCKER}/compartments/{self.COMP}").json()["degraded"] is False


class TestInvalidFaultClearing:
    LOCKER = "L-CLRFAIL"
    COMP = "C1"

    def _setup(self, client: TestClient) -> None:
        client.post("/events", json=compartment_registered(locker_id=self.LOCKER, compartment_id=self.COMP))

    def test_clearing_nonexistent_fault_returns_409(self, client: TestClient) -> None:
        self._setup(client)
        resp = client.post(
            "/events",
            json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=str(uuid.uuid4())),
        )
        assert resp.status_code == 409

    def test_clearing_already_cleared_fault_returns_409(self, client: TestClient) -> None:
        self._setup(client)
        fault_eid = str(uuid.uuid4())
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=2, event_id=fault_eid))
        client.post("/events", json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault_eid))
        # Try to clear again
        resp = client.post(
            "/events",
            json=fault_cleared(locker_id=self.LOCKER, compartment_id=self.COMP, fault_event_id=fault_eid),
        )
        assert resp.status_code == 409

    def test_clearing_fault_from_wrong_compartment_returns_409(self, client: TestClient) -> None:
        self._setup(client)
        client.post("/events", json=compartment_registered(locker_id=self.LOCKER, compartment_id="C2"))
        fault_eid = str(uuid.uuid4())
        client.post("/events", json=fault_reported(locker_id=self.LOCKER, compartment_id=self.COMP, severity=2, event_id=fault_eid))
        # Try to clear using C2 (wrong compartment)
        resp = client.post(
            "/events",
            json=fault_cleared(locker_id=self.LOCKER, compartment_id="C2", fault_event_id=fault_eid),
        )
        assert resp.status_code == 409
