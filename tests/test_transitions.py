"""
Tests for event idempotency and invalid state transitions.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.factories import (
    compartment_registered,
    fault_cleared,
    fault_reported,
    parcel_deposited,
    parcel_picked_up,
    reservation_created,
    reservation_expired,
)


class TestIdempotency:
    """Re-sending the same event_id must not change state."""

    def _setup(self, client: TestClient) -> tuple[str, str]:
        locker_id = "L-IDEM"
        compartment_id = "C1"
        client.post("/events", json=compartment_registered(locker_id=locker_id, compartment_id=compartment_id))
        return locker_id, compartment_id

    def test_duplicate_compartment_registered_returns_200(self, client: TestClient) -> None:
        event = compartment_registered()
        resp1 = client.post("/events", json=event)
        assert resp1.status_code == 202
        resp2 = client.post("/events", json=event)
        assert resp2.status_code == 200

    def test_duplicate_does_not_change_state(self, client: TestClient) -> None:
        locker_id, _ = self._setup(client)
        # Check state before
        summary_before = client.get(f"/lockers/{locker_id}").json()

        # Re-send the registration event – we need to get the actual event_id
        eid = str(uuid.uuid4())
        event = compartment_registered(locker_id=locker_id, compartment_id="C2", event_id=eid)
        client.post("/events", json=event)
        hash_after_first = client.get(f"/lockers/{locker_id}").json()["state_hash"]

        # Re-send the same event
        resp = client.post("/events", json=event)
        assert resp.status_code == 200
        hash_after_second = client.get(f"/lockers/{locker_id}").json()["state_hash"]

        assert hash_after_first == hash_after_second

    def test_duplicate_reservation_returns_200(self, client: TestClient) -> None:
        locker_id, comp_id = self._setup(client)
        res_id = str(uuid.uuid4())
        event = reservation_created(locker_id=locker_id, compartment_id=comp_id, reservation_id=res_id)
        r1 = client.post("/events", json=event)
        assert r1.status_code == 202
        r2 = client.post("/events", json=event)
        assert r2.status_code == 200


class TestInvalidStateTransitions:
    """Domain rule violations must return 409."""

    def _make_locker(self, client: TestClient, locker_id: str = "L-TRANS", comp_id: str = "C1") -> None:
        client.post("/events", json=compartment_registered(locker_id=locker_id, compartment_id=comp_id))

    def test_deposit_before_reservation_returns_409(self, client: TestClient) -> None:
        self._make_locker(client)
        fake_res_id = str(uuid.uuid4())
        resp = client.post("/events", json=parcel_deposited(locker_id="L-TRANS", reservation_id=fake_res_id))
        assert resp.status_code == 409

    def test_pickup_before_deposit_returns_409(self, client: TestClient) -> None:
        self._make_locker(client)
        res_id = str(uuid.uuid4())
        client.post("/events", json=reservation_created(locker_id="L-TRANS", reservation_id=res_id))
        resp = client.post("/events", json=parcel_picked_up(locker_id="L-TRANS", reservation_id=res_id))
        assert resp.status_code == 409

    def test_pickup_after_expiration_returns_409(self, client: TestClient) -> None:
        self._make_locker(client)
        res_id = str(uuid.uuid4())
        client.post("/events", json=reservation_created(locker_id="L-TRANS", reservation_id=res_id))
        client.post("/events", json=reservation_expired(locker_id="L-TRANS", reservation_id=res_id))
        resp = client.post("/events", json=parcel_picked_up(locker_id="L-TRANS", reservation_id=res_id))
        assert resp.status_code == 409

    def test_reservation_on_nonexistent_compartment_returns_409(self, client: TestClient) -> None:
        self._make_locker(client)
        resp = client.post(
            "/events",
            json=reservation_created(locker_id="L-TRANS", compartment_id="GHOST"),
        )
        assert resp.status_code == 409

    def test_double_reservation_same_compartment_returns_409(self, client: TestClient) -> None:
        self._make_locker(client)
        res_id = str(uuid.uuid4())
        client.post("/events", json=reservation_created(locker_id="L-TRANS", reservation_id=res_id))
        resp = client.post(
            "/events",
            json=reservation_created(locker_id="L-TRANS", reservation_id=str(uuid.uuid4())),
        )
        assert resp.status_code == 409

    def test_full_happy_path_succeeds(self, client: TestClient) -> None:
        locker_id = "L-HAPPY"
        comp_id = "C1"
        res_id = str(uuid.uuid4())

        assert client.post("/events", json=compartment_registered(locker_id=locker_id, compartment_id=comp_id)).status_code == 202
        assert client.post("/events", json=reservation_created(locker_id=locker_id, compartment_id=comp_id, reservation_id=res_id)).status_code == 202
        assert client.post("/events", json=parcel_deposited(locker_id=locker_id, reservation_id=res_id)).status_code == 202
        assert client.post("/events", json=parcel_picked_up(locker_id=locker_id, reservation_id=res_id)).status_code == 202

        status = client.get(f"/reservations/{res_id}").json()
        assert status["status"] == "PICKED_UP"

        comp_status = client.get(f"/lockers/{locker_id}/compartments/{comp_id}").json()
        assert comp_status["active_reservation"] is None
