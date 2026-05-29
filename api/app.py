"""
FastAPI application.

Routes are thin: parse → delegate to service → serialize.
All domain logic lives in domain/ and infrastructure/.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response

from api.schemas import (
    CompartmentStatusResponse,
    EventRequest,
    LockerSummaryResponse,
    ReservationStatusResponse,
)
from domain.models import (
    DomainError,
    DomainEvent,
    EventType,
)
from infrastructure.service import LockStreamService

app = FastAPI(title="LockStream API", version="1.0.0")

# Service instance – injected at startup via lifespan or set directly in tests.
_service: LockStreamService | None = None


def get_service() -> LockStreamService:
    if _service is None:
        raise RuntimeError("Service not initialised")
    return _service


def set_service(service: LockStreamService) -> None:
    global _service
    _service = service


# ---------------------------------------------------------------------------
# POST /events
# ---------------------------------------------------------------------------

@app.post("/events", status_code=202)
def ingest_event(event_req: EventRequest, response: Response) -> dict:
    """
    Ingest a domain event.

    - 202: new event accepted
    - 200: duplicate event_id (idempotent, no state change)
    - 409: domain rule violation
    - 422: validation error (handled automatically by FastAPI/Pydantic)
    """
    service = get_service()

    domain_event = DomainEvent(
        event_id=event_req.event_id,
        occurred_at=event_req.occurred_at,
        locker_id=event_req.locker_id,
        type=EventType(event_req.type.value),
        payload=event_req.payload,
    )

    try:
        is_new = service.handle_event(domain_event)
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if not is_new:
        response.status_code = 200
        return {"detail": "Duplicate event; no state change"}

    return {"detail": "Event accepted"}


# ---------------------------------------------------------------------------
# GET /lockers/{locker_id}
# ---------------------------------------------------------------------------

@app.get("/lockers/{locker_id}", response_model=LockerSummaryResponse)
def get_locker_summary(locker_id: str) -> LockerSummaryResponse:
    service = get_service()
    summary = service.get_locker_summary(locker_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Locker '{locker_id}' not found")
    return LockerSummaryResponse(
        locker_id=summary.locker_id,
        compartments=summary.compartments,
        active_reservations=summary.active_reservations,
        degraded_compartments=summary.degraded_compartments,
        state_hash=summary.state_hash,
    )


# ---------------------------------------------------------------------------
# GET /lockers/{locker_id}/compartments/{compartment_id}
# ---------------------------------------------------------------------------

@app.get(
    "/lockers/{locker_id}/compartments/{compartment_id}",
    response_model=CompartmentStatusResponse,
)
def get_compartment_status(locker_id: str, compartment_id: str) -> CompartmentStatusResponse:
    service = get_service()
    status = service.get_compartment_status(locker_id, compartment_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Compartment '{compartment_id}' not found in locker '{locker_id}'",
        )
    return CompartmentStatusResponse(
        compartment_id=status.compartment_id,
        degraded=status.degraded,
        active_reservation=status.active_reservation,
    )


# ---------------------------------------------------------------------------
# GET /reservations/{reservation_id}
# ---------------------------------------------------------------------------

@app.get("/reservations/{reservation_id}", response_model=ReservationStatusResponse)
def get_reservation_status(reservation_id: str) -> ReservationStatusResponse:
    service = get_service()
    status = service.get_reservation_status(reservation_id)
    if status is None:
        raise HTTPException(
            status_code=404, detail=f"Reservation '{reservation_id}' not found"
        )
    return ReservationStatusResponse(
        reservation_id=status.reservation_id,
        status=status.status.value,  # type: ignore[arg-type]
    )
