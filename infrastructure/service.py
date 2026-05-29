"""
Application service (Facade pattern).

Sits between the HTTP layer and the domain. Orchestrates:
  1. Domain rule validation
  2. Event persistence
  3. Projection update

This keeps FastAPI route handlers thin and testable.
"""
from __future__ import annotations

from domain.models import (
    CompartmentStatusView,
    DomainError,
    DomainEvent,
    DuplicateEventError,
    LockerSummary,
    ReservationStatusView,
)
from domain.projection import Projection
from domain.rules import enforce_domain_rules
from infrastructure.event_store import EventStore


class LockStreamService:
    """
    Facade over the domain.

    Patterns used: Facade, Repository (via EventStore).
    """

    def __init__(self, event_store: EventStore, projection: Projection) -> None:
        self._store = event_store
        self._projection = projection

    # ------------------------------------------------------------------
    # Command side
    # ------------------------------------------------------------------

    def handle_event(self, event: DomainEvent) -> bool:
        """
        Ingest a domain event.

        Returns:
            True  – new event, accepted (202).
            False – duplicate event_id (200).
        Raises:
            DomainError – domain rule violation (409).
        """
        # 1. Validate domain rules against current projection state
        enforce_domain_rules(
            event_type=event.type,
            payload=event.payload,
            compartments=self._projection.compartments,
            reservations=self._projection.reservations,
            locker_id=event.locker_id,
            event_id=str(event.event_id),
        )

        # 2. Persist (raises DuplicateEventError if already stored)
        try:
            self._store.append(event)
        except DuplicateEventError:
            return False

        # 3. Update projection incrementally
        self._projection.apply(event)
        return True

    # ------------------------------------------------------------------
    # Query side
    # ------------------------------------------------------------------

    def get_locker_summary(self, locker_id: str) -> LockerSummary | None:
        return self._projection.get_locker_summary(locker_id)

    def get_compartment_status(
        self, locker_id: str, compartment_id: str
    ) -> CompartmentStatusView | None:
        return self._projection.get_compartment_status(locker_id, compartment_id)

    def get_reservation_status(self, reservation_id: str) -> ReservationStatusView | None:
        return self._projection.get_reservation_status(reservation_id)

    # ------------------------------------------------------------------
    # Rebuild (useful for startup or testing equivalence)
    # ------------------------------------------------------------------

    def rebuild_projection(self) -> None:
        """Rebuild the projection from the full event log."""
        self._projection.rebuild(self._store.load_all())
