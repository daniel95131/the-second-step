"""
Domain rule enforcement.

All invariants are derived from the OpenAPI specification and the
exercise requirements. This module is the single place where domain
rules live, keeping FastAPI routes and the projection free of business logic.
"""
from __future__ import annotations

from typing import Any

from domain.models import (
    CompartmentState,
    DomainError,
    EventType,
    ReservationState,
    ReservationStatus,
)

# Severity threshold above which a compartment becomes degraded
DEGRADATION_SEVERITY_THRESHOLD = 3


def validate_compartment_registered(
    payload: dict[str, Any],
    compartments: dict[str, CompartmentState],
    locker_id: str,
) -> None:
    compartment_id: str = payload.get("compartment_id", "")
    if not compartment_id:
        raise DomainError("payload.compartment_id is required for CompartmentRegistered")


def validate_reservation_created(
    payload: dict[str, Any],
    compartments: dict[str, CompartmentState],
    locker_id: str,
) -> None:
    compartment_id: str = payload.get("compartment_id", "")
    reservation_id: str = payload.get("reservation_id", "")

    if not compartment_id:
        raise DomainError("payload.compartment_id is required for ReservationCreated")
    if not reservation_id:
        raise DomainError("payload.reservation_id is required for ReservationCreated")

    key = f"{locker_id}:{compartment_id}"
    compartment = compartments.get(key)
    if compartment is None:
        raise DomainError(
            f"Compartment '{compartment_id}' does not exist in locker '{locker_id}'"
        )
    if compartment.degraded:
        raise DomainError(
            f"Compartment '{compartment_id}' is degraded and cannot accept new reservations"
        )
    if compartment.active_reservation_id is not None:
        raise DomainError(
            f"Compartment '{compartment_id}' already has an active reservation"
        )


def validate_parcel_deposited(
    payload: dict[str, Any],
    reservations: dict[str, ReservationState],
    locker_id: str,
) -> None:
    reservation_id: str = payload.get("reservation_id", "")
    if not reservation_id:
        raise DomainError("payload.reservation_id is required for ParcelDeposited")

    reservation = reservations.get(reservation_id)
    if reservation is None:
        raise DomainError(f"Reservation '{reservation_id}' does not exist")
    if reservation.locker_id != locker_id:
        raise DomainError(
            f"Reservation '{reservation_id}' belongs to a different locker"
        )
    if reservation.status != ReservationStatus.CREATED:
        raise DomainError(
            f"Parcel deposit is only valid for reservations in CREATED state; "
            f"current state: {reservation.status.value}"
        )


def validate_parcel_picked_up(
    payload: dict[str, Any],
    reservations: dict[str, ReservationState],
    locker_id: str,
) -> None:
    reservation_id: str = payload.get("reservation_id", "")
    if not reservation_id:
        raise DomainError("payload.reservation_id is required for ParcelPickedUp")

    reservation = reservations.get(reservation_id)
    if reservation is None:
        raise DomainError(f"Reservation '{reservation_id}' does not exist")
    if reservation.locker_id != locker_id:
        raise DomainError(
            f"Reservation '{reservation_id}' belongs to a different locker"
        )
    if reservation.status == ReservationStatus.EXPIRED:
        raise DomainError(
            f"Reservation '{reservation_id}' has expired and cannot be picked up"
        )
    if reservation.status != ReservationStatus.DEPOSITED:
        raise DomainError(
            f"Parcel pickup is only valid for reservations in DEPOSITED state; "
            f"current state: {reservation.status.value}"
        )


def validate_reservation_expired(
    payload: dict[str, Any],
    reservations: dict[str, ReservationState],
    locker_id: str,
) -> None:
    reservation_id: str = payload.get("reservation_id", "")
    if not reservation_id:
        raise DomainError("payload.reservation_id is required for ReservationExpired")

    reservation = reservations.get(reservation_id)
    if reservation is None:
        raise DomainError(f"Reservation '{reservation_id}' does not exist")
    if reservation.locker_id != locker_id:
        raise DomainError(
            f"Reservation '{reservation_id}' belongs to a different locker"
        )
    if reservation.status not in (ReservationStatus.CREATED,):
        raise DomainError(
            f"Only CREATED reservations can expire; current state: {reservation.status.value}"
        )


def validate_fault_reported(
    payload: dict[str, Any],
    compartments: dict[str, CompartmentState],
    locker_id: str,
) -> None:
    compartment_id: str = payload.get("compartment_id", "")
    severity = payload.get("severity")

    if not compartment_id:
        raise DomainError("payload.compartment_id is required for FaultReported")
    if severity is None:
        raise DomainError("payload.severity is required for FaultReported")
    if not isinstance(severity, int) or severity < 1:
        raise DomainError("payload.severity must be a positive integer")

    key = f"{locker_id}:{compartment_id}"
    if key not in compartments:
        raise DomainError(
            f"Compartment '{compartment_id}' does not exist in locker '{locker_id}'"
        )


def validate_fault_cleared(
    payload: dict[str, Any],
    compartments: dict[str, CompartmentState],
    locker_id: str,
    event_id: str,
) -> None:
    compartment_id: str = payload.get("compartment_id", "")
    fault_event_id: str = payload.get("fault_event_id", "")

    if not compartment_id:
        raise DomainError("payload.compartment_id is required for FaultCleared")
    if not fault_event_id:
        raise DomainError("payload.fault_event_id is required for FaultCleared")

    key = f"{locker_id}:{compartment_id}"
    compartment = compartments.get(key)
    if compartment is None:
        raise DomainError(
            f"Compartment '{compartment_id}' does not exist in locker '{locker_id}'"
        )

    fault = compartment.faults.get(fault_event_id)
    if fault is None:
        raise DomainError(
            f"Fault with event_id '{fault_event_id}' does not exist on compartment '{compartment_id}'"
        )
    if fault.cleared:
        raise DomainError(
            f"Fault '{fault_event_id}' has already been cleared"
        )
    if fault_event_id == event_id:
        raise DomainError("A fault cannot reference itself")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

def enforce_domain_rules(
    event_type: EventType,
    payload: dict[str, Any],
    compartments: dict[str, CompartmentState],
    reservations: dict[str, ReservationState],
    locker_id: str,
    event_id: str,
) -> None:
    """
    Single entry point for domain rule enforcement.
    Raises DomainError on any violation.
    """
    match event_type:
        case EventType.COMPARTMENT_REGISTERED:
            validate_compartment_registered(payload, compartments, locker_id)
        case EventType.RESERVATION_CREATED:
            validate_reservation_created(payload, compartments, locker_id)
        case EventType.PARCEL_DEPOSITED:
            validate_parcel_deposited(payload, reservations, locker_id)
        case EventType.PARCEL_PICKED_UP:
            validate_parcel_picked_up(payload, reservations, locker_id)
        case EventType.RESERVATION_EXPIRED:
            validate_reservation_expired(payload, reservations, locker_id)
        case EventType.FAULT_REPORTED:
            validate_fault_reported(payload, compartments, locker_id)
        case EventType.FAULT_CLEARED:
            validate_fault_cleared(payload, compartments, locker_id, event_id)
