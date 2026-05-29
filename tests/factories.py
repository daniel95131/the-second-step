"""
Test helper factories.

Centralises test-event construction so tests stay readable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compartment_registered(
    locker_id: str = "L1",
    compartment_id: str = "C1",
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "CompartmentRegistered",
        "payload": {"compartment_id": compartment_id},
    }


def reservation_created(
    locker_id: str = "L1",
    compartment_id: str = "C1",
    reservation_id: str | None = None,
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "ReservationCreated",
        "payload": {
            "compartment_id": compartment_id,
            "reservation_id": reservation_id or str(uuid.uuid4()),
        },
    }


def parcel_deposited(
    locker_id: str = "L1",
    reservation_id: str = "RES-1",
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "ParcelDeposited",
        "payload": {"reservation_id": reservation_id},
    }


def parcel_picked_up(
    locker_id: str = "L1",
    reservation_id: str = "RES-1",
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "ParcelPickedUp",
        "payload": {"reservation_id": reservation_id},
    }


def reservation_expired(
    locker_id: str = "L1",
    reservation_id: str = "RES-1",
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "ReservationExpired",
        "payload": {"reservation_id": reservation_id},
    }


def fault_reported(
    locker_id: str = "L1",
    compartment_id: str = "C1",
    severity: int = 3,
    event_id: str | None = None,
) -> dict:
    eid = event_id or str(uuid.uuid4())
    return {
        "event_id": eid,
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "FaultReported",
        "payload": {"compartment_id": compartment_id, "severity": severity},
    }


def fault_cleared(
    locker_id: str = "L1",
    compartment_id: str = "C1",
    fault_event_id: str = "",
    event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "occurred_at": _now(),
        "locker_id": locker_id,
        "type": "FaultCleared",
        "payload": {
            "compartment_id": compartment_id,
            "fault_event_id": fault_event_id,
        },
    }
