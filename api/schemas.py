"""
Pydantic schemas for the HTTP layer.

These map directly to the OpenAPI components/schemas section and are
the boundary between HTTP and the domain.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class EventTypeEnum(str, Enum):
    COMPARTMENT_REGISTERED = "CompartmentRegistered"
    RESERVATION_CREATED = "ReservationCreated"
    PARCEL_DEPOSITED = "ParcelDeposited"
    PARCEL_PICKED_UP = "ParcelPickedUp"
    RESERVATION_EXPIRED = "ReservationExpired"
    FAULT_REPORTED = "FaultReported"
    FAULT_CLEARED = "FaultCleared"


class EventRequest(BaseModel):
    event_id: UUID
    occurred_at: datetime
    locker_id: str
    type: EventTypeEnum
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class LockerSummaryResponse(BaseModel):
    locker_id: str
    compartments: int
    active_reservations: int
    degraded_compartments: int
    state_hash: str


class CompartmentStatusResponse(BaseModel):
    compartment_id: str
    degraded: bool
    active_reservation: str | None


class ReservationStatusEnum(str, Enum):
    CREATED = "CREATED"
    DEPOSITED = "DEPOSITED"
    PICKED_UP = "PICKED_UP"
    EXPIRED = "EXPIRED"


class ReservationStatusResponse(BaseModel):
    reservation_id: str
    status: ReservationStatusEnum
