"""
Application entry point.

Wires together the event store, projection, service, and FastAPI app,
then starts the uvicorn server.
"""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from api.app import app, set_service
from domain.projection import Projection
from infrastructure.event_store import EventStore
from infrastructure.service import LockStreamService

EVENT_LOG_PATH = Path(os.environ.get("LOCKSTREAM_EVENT_LOG", "events.jsonl"))


def create_service(event_log_path: Path = EVENT_LOG_PATH) -> LockStreamService:
    """
    Factory function that constructs a fully-wired service.

    Pattern: Factory
    """
    store = EventStore(path=event_log_path)
    projection = Projection()
    # Rebuild projection from any events already on disk
    projection.rebuild(store.load_all())
    return LockStreamService(event_store=store, projection=projection)


def main() -> None:
    service = create_service()
    set_service(service)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
