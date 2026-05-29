# DECISIONS.md

Trade-offs and reasoning for LockStream.

---

## 1. OpenAPI as single source of truth

All domain concepts — event types, status enums, response fields — are derived
mechanically from the OpenAPI spec.  No field, type, or invariant was invented
beyond what the spec implies or the exercise explicitly states.

**Consequence**: the `Event.payload` is typed as `dict[str, Any]`.  Because the
spec marks it `additionalProperties: true` without nested schemas, defining
fixed payload schemas would be over-specification.  Domain rules instead
validate required payload keys at the rule-enforcement layer.

---

## 2. In-memory projection over SQLAlchemy

The exercise allows SQLAlchemy with in-memory SQLite, but a plain Python
dict-backed projection is simpler, faster, and easier to reason about for this
scope.  The projection indexes compartments by `"{locker_id}:{compartment_id}"`
and reservations by `reservation_id`, giving **O(1)** lookups for every query
endpoint.

SQLAlchemy would add value if: (a) the dataset exceeded available RAM, (b)
cross-process sharing were needed, or (c) ad-hoc SQL queries were required.
None of those apply here.

---

## 3. JSONL event log, not a database

A single JSONL file is the simplest append-only store that survives process
restarts.  Every line is a self-contained JSON object, making it trivially
inspectable with `cat`, `grep`, or `jq`.

**Limitation**: concurrent writers would corrupt the log.  Acceptable for a
single-process exercise server; in production one would use a database
transaction or a message broker.

---

## 4. Idempotency via in-memory set

The event store maintains a `set[str]` of seen `event_id` values loaded at
startup.  Duplicate detection is therefore **O(1)** and survives restarts
(the set is rebuilt from the JSONL file).

A `DuplicateEventError` is raised (not a domain error) and translated to
HTTP 200 at the route level, matching the OpenAPI spec's intent.

---

## 5. Domain validation before persistence

Rules are enforced **before** the event is written to disk.  This means a
rejected event never enters the log, keeping the log a valid history of
accepted facts.

An alternative (validate after appending, roll back on error) would be more
complex with no benefit given the single-writer constraint.

---

## 6. Projection rebuild on startup

`create_service()` calls `projection.rebuild(store.load_all())` unconditionally.
This keeps the startup path simple and correct even after a crash.  For logs
with millions of events a snapshot/checkpoint mechanism would be appropriate,
but that is premature for this exercise.

---

## 7. Fault degradation model

The spec states: *"Compartments with uncleared faults of severity ≥ 3 are
degraded"*.  Faults are stored per-compartment, keyed by their originating
`event_id`.  The `degraded` property is a pure computation over the fault
collection — no separate flag is stored, so it is always consistent.

`FaultCleared.payload.fault_event_id` is the lineage reference required by
the spec.  Clearing a non-existent or already-cleared fault returns 409.

---

## 8. `state_hash` computation

The hash is a SHA-256 over a deterministically sorted JSON snapshot of
compartment states (compartment_id, active_reservation_id, degraded).  This
makes the hash stable across Python runs and independent of insertion order,
enabling meaningful comparison between incremental and rebuilt projections.

---

## 9. OpenAPI spec note

The provided spec uses `nullable: true` on `CompartmentStatus.active_reservation`,
which is an OpenAPI 3.0 convention.  The spec header declares `openapi: 3.1.0`,
where the correct form is `type: ["string", "null"]`.  The spec was committed
as-is (it is authoritative), and the Pydantic model uses `str | None` which
handles both conventions correctly at runtime.

---

## 10. Test design

- **Fixtures** create a fresh in-memory service and JSONL file per test,
  eliminating inter-test state leakage.
- **Factories** (`tests/factories.py`) centralise event construction, keeping
  test bodies focused on behaviour rather than boilerplate.
- **Contract tests** load `openapi.yaml` at session scope and use `jsonschema`
  to validate every response body, ensuring the implementation never drifts
  from the spec.
