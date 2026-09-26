# SmartPark Kenya — Algorithms, Data Structures & Dynamic Database Design

Answers to the assignment, in three parts:

- **(a)** An algorithm for each of the 10 modules, written as pseudocode that matches the shipped code
- **(b)** The data structures used and *why each one was chosen*
- **(c)** A dynamic database design — the schema, how it evolves at runtime, and what keeps it fast and safe

File references are live: every pseudocode block below is implemented at the
path shown. Use-case mapping → `USE_CASES.md`; architecture overview →
`ARCHITECTURE.md`.

---

# (a) Algorithm for each module

## Module 1 — Authentication & Role-Based Access Control

```
LOGIN(username, password):
    user ← SELECT users WHERE username = ?
    if user is None or not verify_hash(password, user.password):
        return "invalid credentials"            # PBKDF2 hash, never plain text
    start signed session cookie (HttpOnly)
    return user

ROLE_GATE(required_roles)(handler):            # decorator applied to a view
    if request.user is not authenticated:
        return REDIRECT /accounts/login/?next=…    # anonymous → login
    if not (user.is_superuser OR user.role IN required_roles):
        return 403 "your role does not permit this action"   # wrong role → 403
    return handler(request)                       # right role → run the view
```

**Why two different failure paths?** Anonymous users simply don't know the
page exists behind a login, so a redirect is friendlier; a signed-in user
who *is* on the wrong role is a real permission problem and deserves an
explicit 403. Keeping them distinct is also what makes the tests
(`UserRoleTests`, `ReportAccessTests`) deterministic.

- Implementation: `django_app/accounts/decorators.py` (`_role_gate`)
- Complexity: O(1) per request (session lookup + role check)

## Module 2 — Slot Management

```
CREATE_SLOT(number, status = AVAILABLE):
    if number EXISTS: reject (unique constraint backstops the form)
    INSERT parking_slots

SET_STATUS(slot, new_status):                  # admin action
    if slot.status = OCCUPIED and new_status ≠ OCCUPIED:
        refuse silent overwrite of a bay that holds a car
        # physical reality: an attendant must confirm the car has gone
    UPDATE parking_slots SET status = new_status WHERE id = slot.id

OCCUPANCY_SUMMARY():                           # one round trip, no N+1
    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE status = 'AVAILABLE'),
           COUNT(*) FILTER (WHERE status = 'OCCUPIED'),
           COUNT(*) FILTER (WHERE status = 'RESERVED'),
           COUNT(*) FILTER (WHERE status = 'OUT_OF_SERVICE')
    FROM parking_slots
```

- Implementation: `django_app/parking/views.py`, `services/occupancy.py`
- Complexity: O(1) summary (single aggregate scan, indexed by `status`)

## Module 3 — Vehicle Entry

```
REGISTER_ENTRY(plate, vehicle_type, user):                  # UC-02
    plate ← NORMALISE(plate)                # upper-case, strip whitespace (A3)
    if plate = ∅: raise ValueError

    BEGIN TRANSACTION
        vehicle ← SELECT vehicles WHERE plate_number = plate
        if vehicle is None: INSERT vehicles (plate, type)     # get_or_create

        if EXISTS (sessions WHERE vehicle = vehicle AND status = 'ACTIVE'):
            raise VehicleAlreadyParkedError      # duplicate-entry guard

        slot ← ALLOCATE_SLOT()                  # see A2 below; locks rows
        if slot = None:
            raise ParkingLotFullError           # rolls the transaction back

        INSERT parking_sessions (vehicle, slot, entry_time = NOW(),
                                 status = 'ACTIVE', registered_by = user)
    COMMIT
    return session

ALLOCATE_SLOT():                                # algorithm A2
    rows ← SELECT * FROM parking_slots
           WHERE status = 'AVAILABLE' ORDER BY slot_number FOR UPDATE
    if rows = ∅: return None
    UPDATE parking_slots SET status = 'OCCUPIED' WHERE id = rows[0].id
    return rows[0]

# after commit (hardware side effect, never inside the transaction):
BARRIER("open")                                 # Module 7
```

- Implementation: `services/entry.py`, `services/allocation.py`
- Complexity: O(n) scan ordered by the `slot_number` index; `FOR UPDATE` makes
  two simultaneous attendants queue instead of both receiving A01

## Module 4 — Vehicle Exit

```
SEARCH(plate):                                  # UC-03, the preview
    plate ← NORMALISE(plate)
    session ← SELECT sessions WHERE vehicle.plate = plate AND status = 'ACTIVE'
    if session is None: return "no active session"
    return QUOTE(session)

QUOTE(session):                                 # read-only preview
    return CALL fee-service(entry_time, NOW())
    # if the service is down → show a warning, allow nothing to be charged

REGISTER_EXIT(session_id, method, user):        # UC-05, algorithm A4
    session ← SELECT sessions WHERE id = session_id AND status = 'ACTIVE'
    if session is None: raise NoActiveSessionError
    exit_time ← NOW()
    duration ← FLOOR((exit_time − entry_time) / 60s)
    fee ← CALL fee-service(entry_time, exit_time)
    if method ∉ {CASH, MPESA, CARD}: raise ValueError

    BEGIN TRANSACTION
        lock session row (FOR UPDATE)
        if status ≠ 'ACTIVE': raise "already completed"     # double-submit
        INSERT payments (session, fee, method, status = 'PAID',
                         paid_at = exit_time, received_by = user)
        UPDATE parking_sessions SET exit_time, duration_minutes = duration,
                                     amount_paid = fee, status = 'COMPLETED'
        RELEASE_SLOT(session.slot)              # OCCUPIED → AVAILABLE
    COMMIT

    BARRIER("open")            # only reached if the commit succeeded
    return session, payment
```

**Ordering is the algorithm.** The barrier opens *on payment*: the fee call
happens before any write (service down ⇒ clean abort), payment + exit + slot
release commit together, and only the committed case reaches the barrier.

- Implementation: `services/exit.py`, `parking/views.py: vehicle_exit()`
- Complexity: O(1) (a few indexed lookups + one aggregate-free write)

## Module 5 — Fee Calculation (Flask microservice)

```
FEE_BRACKETS = [(30, 0), (120, 50), (240, 100), (360, 300), (∞, 500)]

CALCULATE_FEE(duration_minutes):                # algorithm A1 — first match wins
    assert duration_minutes ≥ 0
    for (upper, charge) in FEE_BRACKETS:        # ascending bounds
        if duration_minutes ≤ upper: return charge

PRICE_SESSION(entry, exit):
    duration ← FLOOR((exit − entry) / 60s)
    if duration < 0: raise "exit before entry"
    return {duration_minutes: duration, fee: CALCULATE_FEE(duration)}
```

| Duration | ≤30 min | 31–120 min | 121–240 min | 241–360 min | >360 min |
| --- | --- | --- | --- | --- | --- |
| KES | **0** | **50** | **100** | **300** | **500** |

- Implementation: `flask_services/fee_service/app.py`
- Complexity: O(5) → effectively O(1); every boundary minute (30/31, 120/121,
  240/241, 360/361) is asserted in `tests/test_fee_service.py`

## Module 6 — Payment Management

```
PROCESS_PAYMENT(session, method, fee, user):     # called inside A4's transaction
    if method ∉ {CASH, MPESA, CARD}: raise
    INSERT payments (parking_session_id, amount = fee,
                     payment_method, payment_status = 'PAID',
                     paid_at = NOW(), received_by = user)
    # PENDING / FAILED states exist for the future M-Pesa STK callback:
    # insert PENDING, flip to PAID when the provider confirms.

SETTLED_REVENUE(date_range):
    SELECT SUM(amount) FROM payments
    WHERE payment_status = 'PAID' AND paid_at WITHIN date_range
```

- Implementation: `django_app/payments/models.py`, `services/exit.py`
- Complexity: O(1) insert; revenue reports use the `paid_at` index

## Module 7 — Barrier Control (Flask microservice)

```
BARRIER(command):                               # open | close | status
    call http://barrier-service:5001/api/barrier/{command}
    return (ok: bool, detail: str)

/api/barrier/open  → {status: "success", barrier: "opened"}   # in-memory state
/api/barrier/close → {status: "success", barrier: "closed"}
/api/barrier/status→ {barrier: "opened"|"closed"}
```

Called **after** commit on exit (and after a successful allocation on entry).
A failure never corrupts data — it downgrades the success message to a
warning: *"…recorded, but the barrier did not respond"*.

- Implementation: `flask_services/barrier_service/app.py`,
  `services/clients.py: open_gate()`

## Module 8 — Dashboard

```
DASHBOARD_STATISTICS():                         # six cards, all today-based
    return {
      …occupancy_summary(),                     # Module 2 aggregate
      vehicles_today : COUNT(sessions WHERE entry_time = TODAY),
      exits_today    : COUNT(sessions WHERE exit_time  = TODAY),
      revenue_today  : SUM(payments WHERE status = 'PAID' AND paid_at = TODAY),
      revenue_month  : SUM(payments WHERE status = 'PAID'
                                        AND paid_at = THIS MONTH) }

TREND_SERIES(days = 7):                         # continuous, zero-filled
    start ← TODAY − (days − 1)
    entries ← GROUP sessions BY entry_time::date   (only days with rows)
    exits   ← GROUP sessions BY exit_time::date
    revenue ← GROUP payments BY paid_at::date  (status = 'PAID')
    for offset in 0 … days−1:                   # fill the gaps
        day ← start + offset
        emit {date, label, entries: entries[day] ?? 0,
                       exits: exits[day] ?? 0, revenue: revenue[day] ?? 0.0}
```

**Why zero-fill?** A chart fed only the days that *have* rows silently
compresses quiet days and lies about the trend. Emitting one point per day,
oldest first, keeps the x-axis honest — which matters for a client looking at
"a quiet Sunday vs a busy Saturday".

- Implementation: `dashboard/services.py`
- Complexity: three aggregate queries, O(days) assembly; payload serialised
  with `json_script` (XSS-safe) and drawn by Chart.js

## Module 9 — Reports

```
REPORT_INDEX():                                 # admin only
    figures   ← headline_figures()      # revenue all-time / month / today,
                                        # session counts, avg duration, KES/session
    series    ← REVENUE_SERIES(14)      # same zero-fill trick as A8
    methods   ← SELECT payment_method, SUM(amount), COUNT(*)
                FROM payments WHERE status='PAID'
                GROUP BY payment_method ORDER BY SUM(amount) DESC
    occupancy ← SELECT status, COUNT(*), 100*COUNT(*)/total FROM parking_slots
                GROUP BY status
    sessions  ← SELECT * FROM parking_sessions
                ORDER BY entry_time DESC LIMIT 25
                (select_related vehicle, slot — one query, no N+1)

EXPORT_CSV():                                   # full ledger download
    open response(text/csv, BOM for Excel)
    write header row
    for s IN sessions ORDER BY entry_time DESC:
        write plate, vehicle type, slot, entry, exit, duration,
               amount, status, attendant        # None → "" / "—"
```

- Implementation: `reports/services.py`, `reports/views.py`
- Complexity: O(k) grouping per report; the ledger export streams one ordered
  query

## Module 10 — Public Availability Display

```
DISPLAY():                                      # UC-01, no login
    stats  ← OCCUPANCY_SUMMARY()                # Module 2
    slots  ← SELECT slot_number, status
             FROM parking_slots ORDER BY slot_number
    render counters + one tile per slot:
         AVAILABLE → FREE · OCCUPIED → TAKEN · RESERVED → RESERVED
         OUT_OF_SERVICE → CLOSED
    auto-refresh every 10 s (meta http-equiv=refresh)
```

- Implementation: `dashboard/views.py: display()`,
  `templates/dashboard/display.html`
- Complexity: O(n) render for n slots; single indexed query

### Cross-cutting: test-database lifecycle (dev-ops algorithm)

```
SETUP:    CREATE DATABASE test_postgres → migrate → run tests
TEARDOWN: DROP DATABASE test_postgres WITH (FORCE)   # via 'postgres' maint db
          guard: refuse if name ∈ {postgres, template0, template1}
```

`WITH (FORCE)` terminates leftover pooler sessions so a dropped connection
never blocks teardown — implemented in `tests/runner.py`.

---

# (b) Data structures and the reasons for their use

| # | Data structure | Where it is used | Why this structure |
| --- | --- | --- | --- |
| 1 | **Ordered list of tuples** `(upper_bound, fee)` | Fee brackets (`FEE_BRACKETS`) | The charge table is an *ordered, first-match-wins* rule set. A list preserves the order the rules were written in, is one editable literal, and scanning 5 elements is faster than any index could be. A dictionary keyed by duration would need a key per minute (0…∞) — impossible; a `bisect` on sorted bounds is overkill for 5 rows. |
| 2 | **Hash map / dictionary** `dict[K, V]` | `occupancy_summary()` result, `trend_series` day lookups, `METHOD_LABELS = dict(choices)`, chart payload | O(1) lookup by key. Day→value maps turn "aggregate rows" into "fill 7 slots" in constant time per slot; `dict(choices)` maps an enum code to its human label without if/else chains. |
| 3 | **Set** `PaymentMethod.values`, `SessionStatus.values` | Input validation in `register_exit`, duplicate checks | Membership test in O(1). Rejecting a bogus payment method is one `in` check rather than a chain of comparisons — and it stays correct automatically when a new method is added to the choices. |
| 4 | **Ordered list** (queue semantics) via `ORDER BY slot_number … FOR UPDATE` | Slot allocation (A2) | The database *is* the queue. Ordering gives deterministic first-fit (A01 before A02 — which is exactly the order the public display shows), and the row lock serialises competing attendants, so no two cars are ever handed the same bay. Re-implementing this as an in-process Python queue would break the moment two workers/processes serve the UI. |
| 5 | **Relational tables with foreign keys** (5 tables) | Whole system | The data is inherently relational (a payment *belongs to* a session, a session *references* a vehicle and a slot). FKs give referential integrity for free; `ON DELETE PROTECT` on every FK means financial and occupancy history can never be orphaned by a cascade delete. |
| 6 | **Choice enums (`TextChoices`) + CHECK constraints** | slot status, vehicle type, session status, payment method/status, user role | A *constrained domain* stored as a short string: readable in SQL, exportable to CSV, and impossible to store an invalid value. New states (e.g. `CHARGEBACK`) are one line + one migration. |
| 7 | **`Decimal` for money** | `amount`, `amount_paid`, `FEE_BRACKETS` | Floating point cannot represent 0.10 exactly; parking revenue must add up to the cent. `Decimal` gives exact base-10 arithmetic, and `max_digits=10, decimal_places=2` bounds the column. |
| 8 | **Canonical string key** (normalised plate) | `Vehicle.plate_number` UNIQUE | `KDA 123X` and `KDA123X` must never become two rows, or duplicate-entry detection silently fails. Normalising at both write *and* read, plus a UNIQUE index, makes the key structural rather than something callers must remember. |
| 9 | **Time series as a list of dicts** (one point per day) | Dashboard trend, reports revenue series | A chart needs a *continuous* axis. A list guarantees ordering and position (`series[-1]` = today); the zero-filled gaps keep quiet days visible. Dicts per point (`{date,label,entries,exits,revenue}`) survive the JSON hop to Chart.js without positional bugs. |
| 10 | **Denormalised summary columns** on the session (`duration_minutes`, `amount_paid`) *alongside* the payment row | `parking_sessions` | The payment row is the source of truth for *how* it was paid; the session carries the derived values so reporting, CSV export and dashboards read one row instead of joining + recomputing — and they stay stable even if fee rules change later. |
| 11 | **Indices** — UNIQUE (`slot_number`, `plate_number`, `username`), B-tree on `status`, `entry_time`, `paid_at` | Alloc, duplicate checks, all reports | Allocation does `WHERE status='AVAILABLE' ORDER BY slot_number`; reports filter `paid_at` ranges. Indexes turn these from table scans into index scans — the difference you feel when the client asks "revenue, last 14 days" mid-demo. |
| 12 | **ACID transaction block** (`transaction.atomic`) | `register_entry`, `register_exit`, `release_slot` | Not a textbook structure but the essential one: it groups multi-row writes into an all-or-nothing unit. Without it a crash between "insert payment" and "update session" would bill a driver and still leave the session active. |
| 13 | **Tuple return** `(session, payment)` / `(ok, detail)` | `register_exit`, `open_gate` | Returning a small, immutable composite beats a mutable bag of attributes: callers unpack what they need, and a failure channel (`ok, detail`) carries warnings without raising exceptions for non-fatal hardware trouble. |
| 14 | **Stack-ordered errors / exception hierarchy** | `parking/services/exceptions.py` | A single base with typed children (`VehicleAlreadyParkedError`, `ParkingLotFullError`, `FeeServiceUnavailableError`, `NoActiveSessionError`) lets views branch precisely, while the base class still lets them fall back to one generic handler. |

### Quick summary of the choice rationale

- **Ordered rules** → list (order is meaning)
- **Fast keyed lookups** → dict / set (O(1))
- **Shared mutable state that needs ordering** → database row lock, not memory
- **Money** → `Decimal`, never `float`
- **Identity** → normalised, unique string key
- **Derived numbers** → precomputed columns on the row you read
- **Multi-row correctness** → transaction
- **Charts** → continuous zero-filled list

---

# (c) Dynamic database design

"Dynamic" here means the schema **is not a fixed script the client runs
once** — it is created, evolved, seeded and queried by the running system:
structure comes from migrations, contents from live traffic, capacity from
data, and configuration from the environment.

## C.1 Conceptual model (ER diagram)

```
        users ─────────────┬─────────────────────────┐
        (role)             │ registered_by            │ received_by
                           ▼                          ▼
                   parking_sessions ──────────► payments
                    │            │                 │
          vehicle   │            │ slot            │ amount, method,
                    ▼            ▼                 │ status, paid_at
                vehicles    parking_slots
              (plate, type)  (number, status)
```

| Table | Columns | Keys & constraints |
| --- | --- | --- |
| `users` | id, username, password (hash), role, is_superuser, is_staff, … | **PK** id · **UNIQUE** username · `role ∈ {ADMIN, ATTENDANT}` |
| `parking_slots` | id, slot_number, status, created_at | **PK** id · **UNIQUE** slot_number · `status ∈ {AVAILABLE, OCCUPIED, RESERVED, OUT_OF_SERVICE}` · index on `status` |
| `vehicles` | id, plate_number, vehicle_type, created_at | **PK** id · **UNIQUE** plate_number (stored normalised) · `vehicle_type ∈ {CAR, SUV, VAN, TRUCK, MOTORCYCLE}` |
| `parking_sessions` | id, vehicle_id, slot_id, entry_time, exit_time, duration_minutes, amount_paid, status, registered_by, created_at | **PK** id · **FK** vehicle_id → vehicles **PROTECT** · **FK** slot_id → parking_slots **PROTECT** · **FK** registered_by → users **PROTECT NULL** · `status ∈ {ACTIVE, COMPLETED}` · indexes on `(entry_time)`, `(status)` |
| `payments` | id, parking_session_id, amount, payment_method, payment_status, paid_at, received_by, created_at | **PK** id · **FK** parking_session_id → parking_sessions **PROTECT** · **FK** received_by → users **PROTECT NULL** · `payment_method ∈ {CASH, MPESA, CARD}` · `payment_status ∈ {PENDING, PAID, FAILED}` · index on `(paid_at)` |

Cardinality: `vehicles 1 ─ ∞ parking_sessions`, `parking_slots 1 ─ ∞
parking_sessions`, `parking_sessions 1 ─ ∞ payments`, `users 1 ─ ∞ sessions
(as attendant)` and `users 1 ─ ∞ payments (as receiver)`.

A car may revisit (many sessions per vehicle); a bay is reused over time
(many sessions per slot); a stay may involve several payments later
(refunds/adjustments) — which is why the FK points payment → session, never
the other way.

## C.2 Physical design — why these choices

1. **PostgreSQL (Supabase) as the single source of truth.** One database
   serving Django *and* readable by reporting tools. The two Flask services
   deliberately never touch it — they stay stateless so fees and barrier
   simulation are trivially scalable and re-deployable.
2. **`ON DELETE PROTECT` everywhere.** Deleting a vehicle or a slot that has
   history raises an error instead of erasing revenue records. Auditability
   beats convenience in a system that handles money.
3. **Enum-as-VARCHAR + CHECK/choices.** Portable across SQLite (local
   bootstrap) and Postgres (production), human-readable in SQL and CSV, and
   extensible by one migration.
4. **Timestamps in one timezone.** Every `entry_time`/`exit_time`/`paid_at`
   is a `timestamptz` written with `timezone.now()`, so duration maths and
   "today" grouping never drift.
5. **Money as `NUMERIC(10,2)`.** Exact; survives `SUM()`, CSV export and
   round-trips without rounding drift.

## C.3 Dynamic behaviour — how the design adapts at runtime

| Dynamic aspect | Mechanism |
| --- | --- |
| **Schema creation** | `python manage.py migrate` — versioned migration files (`accounts/0001_initial`, `parking/0001_initial`, …) create tables; the structure can be altered without downtime and rolled forward/back. |
| **Configuration** | `DATABASE_URL` read from `.env` (`dj-database-url`). Swap SQLite → Supabase by setting one variable; **no code change**. Session-pooler host/IPv4 handled by the same setting. |
| **Capacity** | Slots are *rows, not schema*. The operator adds/removes bays at runtime (`seed_slots`, admin, or `POST /parking/slots/new/`) and the display, allocation and statistics pick them up on the next query — no redeploy. |
| **Live state** | Slot `status` and session `status` mutate continuously (AVAILABLE→OCCUPIED→AVAILABLE; ACTIVE→COMPLETED). All screens read current state with aggregate queries — nothing is cached into stale columns. |
| **Historical reporting** | `paid_at`/`entry_time` indexes + `GROUP BY` generate day/month series on demand, so any date range can be asked for without a pre-aggregated table. |
| **Extensibility for M-Pesa STK** | `payment_status` already has `PENDING/FAILED` and the model reserves room for a `provider_reference` column: add the field by migration, insert `PENDING`, flip to `PAID` on callback — schema and code already anticipate it. |
| **Elastic test environments** | The suite creates `test_postgres`, migrates it, and `DROP DATABASE … WITH (FORCE)` afterwards — a full, isolated database per run (guarded so it can never target a real one). |
| **Zero-downtime evolution** | Because every change is a migration, the running app and the new schema can coexist during deploy; additive columns (nullable/defaulted) are applied first, code second. |

## C.4 Data lifecycle (the dynamic flow)

```
 driver reads /display ─┐
                        │ 10 s refresh, read-only
 attendant posts entry ─┼─► vehicles ↑  parking_slots ←ALLOCATE (lock)
                        │      └─────► parking_sessions (ACTIVE, entry_time=now)
 driver reaches exit ───┼─► QUOTE (fee service, read-only)
 attendant posts payment┼─► payments (PAID) + session COMPLETED + slot AVAILABLE
                        │        └─► after commit: barrier OPEN
 admin opens /reports ──┴─► aggregate reads over payments + sessions (no writes)
```

Reads (display, dashboard, reports) and writes (entry, exit) are independent
queries over the same tables — the system is *dynamic* in the sense that any
of the six screens can change any row at any moment, and consistency is
protected by row locks and transactions rather than by application-level
bookkeeping.

## C.5 Integrity guarantees (summary)

| Threat | Defence |
| --- | --- |
| Same slot given to two cars | `FOR UPDATE` row lock inside `transaction.atomic` (A2) |
| Double exit / double payment | status re-checked under lock; unique ACTIVE session per vehicle |
| Money rounding errors | `NUMERIC(10,2)` + `Decimal` arithmetic |
| Wrong-role access | decorator returns 403; anonymous → login |
| Plate variants creating duplicates | normalisation at write *and* read + UNIQUE index |
| Orphaned financial history | `ON DELETE PROTECT` on all FKs |
| Fee service outage billing wrong | fee computed before any write → clean abort, nothing committed |
| Barrier opening without payment | barrier commanded only after commit (A4) |
| Lost updates from concurrent screens | whole exit is one transaction; hardware effects strictly outside it |

---

## Where each piece lives

| Part | Code |
| --- | --- |
| M1 role gate | `django_app/accounts/decorators.py` |
| M2 slots + occupancy | `django_app/parking/views.py`, `services/occupancy.py` |
| M3 entry | `django_app/parking/services/entry.py`, `services/allocation.py` |
| M4 exit | `django_app/parking/services/exit.py` |
| M5 fees | `flask_services/fee_service/app.py` |
| M6 payments | `django_app/payments/models.py` |
| M7 barrier | `flask_services/barrier_service/app.py`, `services/clients.py` |
| M8 dashboard | `django_app/dashboard/services.py` |
| M9 reports | `django_app/reports/services.py` |
| M10 display | `django_app/dashboard/views.py`, `templates/dashboard/display.html` |
| Schema & migrations | `django_app/*/migrations/`, config in `django_app/settings.py` |

**Verification:** every algorithm above is covered by the 70-test suite —
`python manage.py test tests`.
