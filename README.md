# LockStream

A small event-sourced backend service for smart parcel locker management.

---

## Quick start

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
``` 

### 2. Run the API

```bash
python main.py
```

The server starts on `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

Optional environment variable:

```bash
LOCKSTREAM_EVENT_LOG=/path/to/events.jsonl python main.py
```

The service will replay any existing events from the log on startup,
so state survives restarts automatically.

---

## Running tests

```bash
pytest -v
```

Expected output covers five test modules:

| Module | What it tests |
|---|---|
| `test_contract.py` | OpenAPI request validation (422) and response schema conformance |
| `test_transitions.py` | Idempotency and invalid state transitions |
| `test_faults.py` | Fault degradation, threshold, and clearing rules |
| `test_projection.py` | Incremental vs full-rebuild state equivalence |

---

## API overview

All contracts are defined in `openapi.yaml`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/events` | Ingest a domain event |
| `GET` | `/lockers/{locker_id}` | Locker summary |
| `GET` | `/lockers/{locker_id}/compartments/{compartment_id}` | Compartment status |
| `GET` | `/reservations/{reservation_id}` | Reservation status |

### Example: register a compartment

```bash
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "occurred_at": "2024-06-01T10:00:00Z",
    "locker_id": "locker-A",
    "type": "CompartmentRegistered",
    "payload": {"compartment_id": "box-1"}
  }'
```

---

## Architecture

```
lockstream/
├── domain/
│   ├── models.py       # Value objects, state records, read models, exceptions
│   ├── rules.py        # Domain invariant enforcement
│   └── projection.py   # In-memory state projection
├── infrastructure/
│   ├── event_store.py  # Append-only JSONL event store (Repository pattern)
│   └── service.py      # Application service / Facade
├── api/
│   ├── schemas.py      # Pydantic request/response models
│   └── app.py          # FastAPI routes
├── tests/
│   ├── conftest.py     # pytest fixtures
│   ├── factories.py    # Test event builders
│   ├── test_contract.py
│   ├── test_transitions.py
│   ├── test_faults.py
│   └── test_projection.py
├── main.py             # Entry point / wiring (Factory pattern)
└── openapi.yaml        # Authoritative API contract
```

The architecture enforces a strict dependency direction:

```
api → infrastructure → domain
```

Domain code has zero dependencies on FastAPI, the event store, or any I/O.

### Design patterns used

- **Repository** (`EventStore`): abstracts event persistence behind `append / load_all / load_by_locker`.
- **Facade** (`LockStreamService`): single entry point for the HTTP layer; hides the orchestration of validation → persistence → projection update.
- **Factory** (`create_service` in `main.py`): constructs the fully-wired object graph and replays the event log before serving traffic.
