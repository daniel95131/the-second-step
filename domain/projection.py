"""
In-memory projection.

Applies domain events to build queryable state.  Supports both full
rebuild (O(N)) and incremental application.  All lookups are O(1).
"""
from __future__ import annotations

from typing import Iterable

from domain.models import (
    CompartmentState,
    CompartmentStatusView,
    DomainEvent,
    EventType,
    FaultRecord,
    LockerSummary,
    ReservationState,
    ReservationStatus,
    ReservationStatusView,
    compute_state_hash,
)


class Projection:
    """
    Maintains indexed in-memory state derived from the event stream.

    Index keys:
      - compartments: "{locker_id}:{compartment_id}"
      - reservations: "{reservation_id}"
      - locker_compartments: "{locker_id}" → set of compartment keys
    """

    def __init__(self) -> None:
        self._compartments: dict[str, CompartmentState] = {}
        self._reservations: dict[str, ReservationState] = {}
        # locker_id → set of composite compartment keys
        self._locker_compartment_index: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild(self, events: Iterable[DomainEvent]) -> None:
        """Full O(N) rebuild: clear state and replay every event."""
        self._compartments.clear()
        self._reservations.clear()
        self._locker_compartment_index.clear()
        for event in events:
            self.apply(event)

    def apply(self, event: DomainEvent) -> None:
        """Incrementally apply a single event."""
        match event.type:
            case EventType.COMPARTMENT_REGISTERED:
                self._on_compartment_registered(event)
            case EventType.RESERVATION_CREATED:
                self._on_reservation_created(event)
            case EventType.PARCEL_DEPOSITED:
                self._on_parcel_deposited(event)
            case EventType.PARCEL_PICKED_UP:
                self._on_parcel_picked_up(event)
            case EventType.RESERVATION_EXPIRED:
                self._on_reservation_expired(event)
            case EventType.FAULT_REPORTED:
                self._on_fault_reported(event)
            case EventType.FAULT_CLEARED:
                self._on_fault_cleared(event)

    # ------------------------------------------------------------------
    # Queries  (O(1))
    # ------------------------------------------------------------------

    def get_locker_summary(self, locker_id: str) -> LockerSummary | None:
        keys = self._locker_compartment_index.get(locker_id)
        if keys is None:
            return None
        compartments_for_locker = {k: self._compartments[k] for k in keys}
        active = sum(
            1 for c in compartments_for_locker.values()
            if c.active_reservation_id is not None
        )
        degraded = sum(
            1 for c in compartments_for_locker.values() if c.degraded
        )
        return LockerSummary(
            locker_id=locker_id,
            compartments=len(keys),
            active_reservations=active,
            degraded_compartments=degraded,
            state_hash=compute_state_hash(compartments_for_locker),
        )

    def get_compartment_status(
        self, locker_id: str, compartment_id: str
    ) -> CompartmentStatusView | None:
        key = f"{locker_id}:{compartment_id}"
        c = self._compartments.get(key)
        if c is None:
            return None
        return CompartmentStatusView(
            compartment_id=c.compartment_id,
            degraded=c.degraded,
            active_reservation=c.active_reservation_id,
        )

    def get_reservation_status(self, reservation_id: str) -> ReservationStatusView | None:
        r = self._reservations.get(reservation_id)
        if r is None:
            return None
        return ReservationStatusView(
            reservation_id=r.reservation_id,
            status=r.status,
        )

    # Expose internal state for domain rule validation (read-only references)
    @property
    def compartments(self) -> dict[str, CompartmentState]:
        return self._compartments

    @property
    def reservations(self) -> dict[str, ReservationState]:
        return self._reservations

    # ------------------------------------------------------------------
    # Private event handlers
    # ------------------------------------------------------------------

    def _on_compartment_registered(self, event: DomainEvent) -> None:
        compartment_id: str = event.payload["compartment_id"]
        key = f"{event.locker_id}:{compartment_id}"
        # Idempotent: if already exists, ignore
        if key not in self._compartments:
            self._compartments[key] = CompartmentState(
                compartment_id=compartment_id,
                locker_id=event.locker_id,
            )
            self._locker_compartment_index.setdefault(event.locker_id, set()).add(key)

    def _on_reservation_created(self, event: DomainEvent) -> None:
        compartment_id: str = event.payload["compartment_id"]
        reservation_id: str = event.payload["reservation_id"]
        key = f"{event.locker_id}:{compartment_id}"
        compartment = self._compartments[key]
        compartment.active_reservation_id = reservation_id
        self._reservations[reservation_id] = ReservationState(
            reservation_id=reservation_id,
            locker_id=event.locker_id,
            compartment_id=compartment_id,
            status=ReservationStatus.CREATED,
        )

    def _on_parcel_deposited(self, event: DomainEvent) -> None:
        reservation_id: str = event.payload["reservation_id"]
        reservation = self._reservations[reservation_id]
        reservation.status = ReservationStatus.DEPOSITED

    def _on_parcel_picked_up(self, event: DomainEvent) -> None:
        reservation_id: str = event.payload["reservation_id"]
        reservation = self._reservations[reservation_id]
        reservation.status = ReservationStatus.PICKED_UP
        key = f"{reservation.locker_id}:{reservation.compartment_id}"
        self._compartments[key].active_reservation_id = None

    def _on_reservation_expired(self, event: DomainEvent) -> None:
        reservation_id: str = event.payload["reservation_id"]
        reservation = self._reservations[reservation_id]
        reservation.status = ReservationStatus.EXPIRED
        key = f"{reservation.locker_id}:{reservation.compartment_id}"
        self._compartments[key].active_reservation_id = None

    def _on_fault_reported(self, event: DomainEvent) -> None:
        compartment_id: str = event.payload["compartment_id"]
        severity: int = int(event.payload["severity"])
        key = f"{event.locker_id}:{compartment_id}"
        compartment = self._compartments[key]
        compartment.faults[str(event.event_id)] = FaultRecord(
            event_id=str(event.event_id),
            severity=severity,
        )

    def _on_fault_cleared(self, event: DomainEvent) -> None:
        compartment_id: str = event.payload["compartment_id"]
        fault_event_id: str = event.payload["fault_event_id"]
        key = f"{event.locker_id}:{compartment_id}"
        compartment = self._compartments[key]
        if fault_event_id in compartment.faults:
            compartment.faults[fault_event_id].cleared = True
