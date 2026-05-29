"""
Append-only event store backed by a JSONL file.

Responsibilities:
- Persist events durably (one JSON object per line).
- Guarantee idempotency via an in-memory event_id index.
- Support full and per-locker replay.

Pattern: Repository
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from domain.models import DomainEvent, DuplicateEventError


class EventStore:
    """
    Append-only event store.

    Thread-safety is deliberately out of scope for this exercise
    (single-process, single-threaded FastAPI dev server).
    """

    def __init__(self, path: Path | str = "events.jsonl") -> None:
        self._path = Path(path)
        # In-memory index: event_id (str) → line offset for O(1) duplicate check
        self._seen: set[str] = set()
        self._events: list[DomainEvent] = []
        self._load_existing()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def append(self, event: DomainEvent) -> bool:
        """
        Append an event to the log.

        Returns:
            True  – event was new and appended.
            False – event_id already exists (idempotent, no-op).
        Raises:
            DuplicateEventError when the event_id is already stored.
        """
        key = str(event.event_id)
        if key in self._seen:
            raise DuplicateEventError(f"event_id '{key}' already stored")

        line = json.dumps(event.to_dict(), separators=(",", ":"))
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

        self._seen.add(key)
        self._events.append(event)
        return True

    def load_all(self) -> list[DomainEvent]:
        """Return all stored events in insertion order."""
        return list(self._events)

    def load_by_locker(self, locker_id: str) -> list[DomainEvent]:
        """Return all events for a specific locker (O(N) scan; acceptable for exercise scope)."""
        return [e for e in self._events if e.locker_id == locker_id]

    def __len__(self) -> int:
        return len(self._events)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_existing(self) -> None:
        """Bootstrap in-memory state from an existing JSONL file."""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                event = DomainEvent.from_dict(data)
                key = str(event.event_id)
                if key not in self._seen:
                    self._seen.add(key)
                    self._events.append(event)
