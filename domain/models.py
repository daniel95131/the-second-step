"""
Domain models derived strictly from the OpenAPI specification.
All concepts, identifiers, and state transitions map to API-defined types.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


# ---------------------------------------------------------------------------
# Enums (sourced from OpenAPI Event.type enum and ReservationStatus.status)
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    COMPARTMENT_REGISTERED = "CompartmentRegistered"
    RESERVATION_CREATED = "ReservationCreated"
    PARCEL_DEPOSITED = "ParcelDeposited"
    PARCEL_PICKED_UP = "ParcelPickedUp"
    RESERVATION_EXPIRED = "ReservationExpired"
    FAULT_REPORTED = "FaultReported"
    FAULT_CLEARED = "FaultCleared"


class ReservationStatus(str, Enum):
    CREATED = "CREATED"
    DEPOSITED = "DEPOSITED"
    PICKED_UP = "PICKED_UP"
    EXPIRED = "EXPIRED"


# ---------------------------------------------------------------------------
# Domain event (maps directly to OpenAPI Event schema)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID
    occurred_at: datetime
    locker_id: str
    type: EventType
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "occurred_at": self.occurred_at.isoformat(),
            "locker_id": self.locker_id,
            "type": self.type.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        return cls(
            event_id=UUID(data["event_id"]),
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            locker_id=data["locker_id"],
            type=EventType(data["type"]),
            payload=data["payload"],
        )


# ---------------------------------------------------------------------------
# Internal state objects (used by the projection, not exposed as-is)
# ---------------------------------------------------------------------------

@dataclass
class FaultRecord:
    """Tracks an individual reported fault."""
    event_id: str          # The event_id of the FaultReported event
    severity: int
    cleared: bool = False


@dataclass
class CompartmentState:
    """Mutable compartment projection state."""
    compartment_id: str
    locker_id: str
    active_reservation_id: str | None = None
    faults: dict[str, FaultRecord] = field(default_factory=dict)  # keyed by fault event_id

    @property
    def degraded(self) -> bool:
        """A compartment is degraded if it has any uncleared fault with severity >= 3."""
        return any(
            f.severity >= 3 for f in self.faults.values() if not f.cleared
        )


@dataclass
class ReservationState:
    """Mutable reservation projection state."""
    reservation_id: str
    locker_id: str
    compartment_id: str
    status: ReservationStatus = ReservationStatus.CREATED


# ---------------------------------------------------------------------------
# Read models (map to OpenAPI response schemas)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LockerSummary:
    locker_id: str
    compartments: int
    active_reservations: int
    degraded_compartments: int
    state_hash: str


@dataclass(frozen=True)
class CompartmentStatusView:
    compartment_id: str
    degraded: bool
    active_reservation: str | None


@dataclass(frozen=True)
class ReservationStatusView:
    reservation_id: str
    status: ReservationStatus


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """Raised when a domain invariant is violated (maps to HTTP 409)."""


class CompartmentNotFoundError(DomainError):
    pass


class ReservationNotFoundError(DomainError):
    pass


class DuplicateEventError(Exception):
    """Raised when an event_id has already been stored (maps to HTTP 200)."""


def compute_state_hash(compartments: dict[str, CompartmentState]) -> str:
    """Deterministic hash of the current compartment state for a locker."""
    snapshot = sorted(
        [
            {
                "compartment_id": c.compartment_id,
                "active_reservation_id": c.active_reservation_id,
                "degraded": c.degraded,
            }
            for c in compartments.values()
        ],
        key=lambda x: x["compartment_id"],
    )
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
