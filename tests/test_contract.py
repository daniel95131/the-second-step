"""
OpenAPI contract tests.

1. Requests violating the OpenAPI schema must return 422.
2. Valid requests must conform exactly to the response schemas.

We load openapi.yaml and use jsonschema to validate response bodies.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import validate as jsonschema_validate

from tests.factories import compartment_registered, reservation_created

OPENAPI_PATH = Path(__file__).parent.parent / "openapi.yaml"


@pytest.fixture(scope="session")
def openapi_spec() -> dict:
    with OPENAPI_PATH.open() as fh:
        return yaml.safe_load(fh)


def resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a simple $ref like '#/components/schemas/LockerSummary'."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node[part]
    return node


# ---------------------------------------------------------------------------
# 422 – schema violations
# ---------------------------------------------------------------------------

class TestContractValidation:
    def test_missing_event_id_returns_422(self, client: TestClient) -> None:
        payload = {
            "occurred_at": "2024-01-01T00:00:00Z",
            "locker_id": "L1",
            "type": "CompartmentRegistered",
            "payload": {"compartment_id": "C1"},
        }
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_invalid_uuid_returns_422(self, client: TestClient) -> None:
        payload = {
            "event_id": "not-a-uuid",
            "occurred_at": "2024-01-01T00:00:00Z",
            "locker_id": "L1",
            "type": "CompartmentRegistered",
            "payload": {"compartment_id": "C1"},
        }
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_invalid_event_type_returns_422(self, client: TestClient) -> None:
        payload = {
            "event_id": str(uuid.uuid4()),
            "occurred_at": "2024-01-01T00:00:00Z",
            "locker_id": "L1",
            "type": "UnknownEventType",
            "payload": {},
        }
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_missing_payload_returns_422(self, client: TestClient) -> None:
        payload = {
            "event_id": str(uuid.uuid4()),
            "occurred_at": "2024-01-01T00:00:00Z",
            "locker_id": "L1",
            "type": "CompartmentRegistered",
        }
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_invalid_datetime_returns_422(self, client: TestClient) -> None:
        payload = {
            "event_id": str(uuid.uuid4()),
            "occurred_at": "not-a-date",
            "locker_id": "L1",
            "type": "CompartmentRegistered",
            "payload": {"compartment_id": "C1"},
        }
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response schema conformance
# ---------------------------------------------------------------------------

class TestResponseSchemas:
    def _register_compartment(self, client: TestClient, locker: str = "L1", comp: str = "C1") -> None:
        resp = client.post("/events", json=compartment_registered(locker_id=locker, compartment_id=comp))
        assert resp.status_code == 202

    def test_locker_summary_conforms_to_schema(
        self, client: TestClient, openapi_spec: dict
    ) -> None:
        self._register_compartment(client)
        resp = client.get("/lockers/L1")
        assert resp.status_code == 200
        schema = resolve_ref(openapi_spec, "#/components/schemas/LockerSummary")
        jsonschema_validate(instance=resp.json(), schema=schema)

    def test_compartment_status_conforms_to_schema(
        self, client: TestClient, openapi_spec: dict
    ) -> None:
        self._register_compartment(client)
        resp = client.get("/lockers/L1/compartments/C1")
        assert resp.status_code == 200
        schema = resolve_ref(openapi_spec, "#/components/schemas/CompartmentStatus")
        jsonschema_validate(instance=resp.json(), schema=schema)

    def test_reservation_status_conforms_to_schema(
        self, client: TestClient, openapi_spec: dict
    ) -> None:
        self._register_compartment(client)
        res_id = str(uuid.uuid4())
        client.post(
            "/events",
            json=reservation_created(reservation_id=res_id),
        )
        resp = client.get(f"/reservations/{res_id}")
        assert resp.status_code == 200
        schema = resolve_ref(openapi_spec, "#/components/schemas/ReservationStatus")
        jsonschema_validate(instance=resp.json(), schema=schema)

    def test_locker_summary_has_required_fields(self, client: TestClient) -> None:
        self._register_compartment(client)
        data = client.get("/lockers/L1").json()
        assert "locker_id" in data
        assert "compartments" in data
        assert "active_reservations" in data
        assert "degraded_compartments" in data
        assert "state_hash" in data

    def test_compartment_status_has_required_fields(self, client: TestClient) -> None:
        self._register_compartment(client)
        data = client.get("/lockers/L1/compartments/C1").json()
        assert "compartment_id" in data
        assert "degraded" in data
        assert "active_reservation" in data

    def test_404_for_unknown_locker(self, client: TestClient) -> None:
        resp = client.get("/lockers/NONEXISTENT")
        assert resp.status_code == 404

    def test_404_for_unknown_compartment(self, client: TestClient) -> None:
        self._register_compartment(client)
        resp = client.get("/lockers/L1/compartments/NONEXISTENT")
        assert resp.status_code == 404

    def test_404_for_unknown_reservation(self, client: TestClient) -> None:
        resp = client.get(f"/reservations/{uuid.uuid4()}")
        assert resp.status_code == 404
