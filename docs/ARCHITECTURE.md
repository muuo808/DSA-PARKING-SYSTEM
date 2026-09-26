# SmartPark Kenya – Architecture

## Stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Core business system | **Django 6.1** | Auth, user management, parking management, reports, dashboard analytics, API layer |
| Microservices | **Flask 3.1** | Barrier control, fee calculation, hardware/IoT simulation |
| Database | **Supabase PostgreSQL** | Single source of truth for all records |
| Frontend | Django Templates + Bootstrap 5 + vanilla JS | Flat, modern UI (no React) |

Communication between Django and Flask uses REST/JSON over HTTP.

```
                     ┌──────────────────────────────────────────┐
  Browser ──────────▶│  Django  :8000                           │
  (templates)        │  ├─ accounts   (auth, roles)             │
                     │  ├─ parking    (slots, vehicles, sessions)│
                     │  ├─ payments   (payment records)         │
                     │  ├─ dashboard  (stats, public display)   │
                     │  ├─ reports    (daily/monthly/history)   │
                     │  └─ api        (/api/v1/ JSON)           │
                     └───────┬───────────────────┬──────────────┘
                             │                   │ REST (outbound)
                             ▼                   ▼
                  ┌─────────────────┐   ┌──────────────────────┐
                  │ Supabase        │   │ Flask fee service    │
                  │ PostgreSQL      │   │ :5000 /api/calculate-fee
                  └─────────────────┘   ├──────────────────────┤
                                        │ Flask barrier service│
                                        │ :5001 /api/barrier/* │
                                        └──────────────────────┘
```

**Rule:** Flask services never touch the database. Django owns all data;
Flask owns stateless computation (fees) and device simulation (barriers).

## Database schema (Supabase)

| Table | Key fields | Notes |
| --- | --- | --- |
| `users` | username, email, password_hash, role, created_at | Custom `AbstractUser`, hashed passwords only |
| `parking_slots` | slot_number, status, created_at | AVAILABLE / OCCUPIED / RESERVED / OUT_OF_SERVICE |
| `vehicles` | plate_number, vehicle_type, created_at | Plate normalised to upper case |
| `parking_sessions` | vehicle_id, slot_id, entry_time, exit_time, duration_minutes, amount_paid, status | ACTIVE / COMPLETED |
| `payments` | parking_session_id, amount, payment_method, payment_status, paid_at | CASH / M-Pesa / Card |

Configuration is environment-driven — `DATABASE_URL` in `.env`:

```bash
# Supabase (Dashboard → Settings → Database → Connection string → URI, Session mode 5432)
DATABASE_URL=postgresql://postgres.xxxx:password@aws-0.xx.pooler.supabase.com:5432/postgres?sslmode=require
```

While `DATABASE_URL` is empty the project falls back to SQLite for local
bootstrap. **Drop the Supabase URI into `.env` and run `manage.py migrate`**
— no code changes required.

## Algorithms

Four algorithms carry the brief. Each is implemented once, in one place, and
covered by tests (see `USE_CASES.md` for the mapping).

### A1 – Parking fee calculation (Module 5)

*Bracket lookup — first match wins.* The charge table is an ordered list of
`(upper_bound_minutes, fee)` pairs, so the scan is constant work (5 rules)
and the table is edited in one literal.

```
FEE_BRACKETS = [(30, 0), (120, 50), (240, 100), (360, 300), (∞, 500)]

fee(duration):
    assert duration >= 0
    for (upper, charge) in FEE_BRACKETS:      # ascending bounds
        if duration <= upper:
            return charge
```

`duration = floor((exit_time − entry_time) / 60s)`; a negative duration is
rejected (`exit before entry` is invalid input).

| Duration | 0–30 min | 31–120 min | 121–240 min | 241–360 min | > 360 min |
| --- | --- | --- | --- | --- | --- |
| KES | **0** | **50** | **100** | **300** | **500** |

Complexity: O(5) → O(1). Every bracket *and* each boundary minute
(30/31, 120/121, 240/241, 360/361) is asserted in `tests/test_fee_service.py`.

### A2 – Slot allocation without double-booking (Module 2/3)

Greedy first-fit over ordered slot numbers, serialised by a row lock.

```
allocate_slot():                              # inside BEGIN
    rows = SELECT * FROM parking_slots
           WHERE status = 'AVAILABLE'
           ORDER BY slot_number
           FOR UPDATE                          # row lock (PostgreSQL)
    if rows is empty: return None             # lot full → caller raises
    UPDATE parking_slots SET status = 'OCCUPIED' WHERE id = rows[0].id
    COMMIT
    return rows[0]
```

- `ORDER BY slot_number` → deterministic, fills A01, A02, … in order (nice
  for the display map).
- `FOR UPDATE` → two attendants submitting at the same instant queue on the
  first row instead of both receiving slot A01. On backends without the
  feature (SQLite bootstrap) the lock is skipped — `connection.features.has_select_for_update`
  guards it.
- `release_slot()` is the mirror operation (`OCCUPIED → AVAILABLE`) and is
  called exactly once, from `register_exit`.

Complexity: O(n) scan ordered by the `slot_number` index.

### A3 – Plate normalisation (Module 3)

Canonical form = **upper case, no whitespace**: `  kda 123x ` → `KDA123X`.

```
normalise_plate(s) = "".join(s.split()).upper()
```

Applied at two chokepoints — `Vehicle.save()` (so a row can only ever hold
the canonical value) and `register_entry()` / `get_active_session()` (so
lookups match). This is what makes duplicate-entry detection reliable:
`KDA 123X` and `KDA123X` can never become two vehicle rows. Complexity:
O(len).

### A4 – Atomic exit: pay first, then barrier (Modules 4/6/7)

The brief requires the barrier to open *on payment*, so ordering is the
algorithm:

```
register_exit(session_id, method, user):       # inside BEGIN
    session = SELECT … FOR UPDATE WHERE id = … AND status = 'ACTIVE'
    if session is None: raise NoActiveSessionError
    fee = CALL fee-service(entry_time, now)     # read-only; down → abort, DB untouched
    INSERT payments (status = 'PAID', paid_at = now)
    UPDATE parking_sessions SET exit_time, duration_minutes,
           amount_paid, status = 'COMPLETED'
    UPDATE parking_slots SET status = 'AVAILABLE'    # release_slot()
    COMMIT                                       # everything lands together

# AFTER the commit — a hardware side effect can never be rolled back:
if payment_succeeded: CALL barrier-service /api/barrier/open
```

Invariants:

1. **Fail closed** – fee service down ⇒ no payment row, no exit, no barrier.
2. **All-or-nothing** – payment + exit + slot release commit together; a
   failure leaves the session ACTIVE and the slot OCCUPIED.
3. **Barrier after commit** – the open command is issued by the view only on
   success; a barrier fault surfaces as a warning *without* corrupting the
   already-recorded exit.

### Database ER diagram (Supabase)

```
users ────────┬─< parking_sessions >────────┐
(registered_by)│                            │
              │              vehicles >────┘
              │                 │
              └─< payments >────┘ (received_by → users)
                    │
                    └── parking_sessions (PROTECT on every FK)
```

| Table | Columns | Constraints |
| --- | --- | --- |
| `users` | id, username, password, role, is_superuser, … | `role ∈ {ADMIN, ATTENDANT}` |
| `parking_slots` | id, slot_number, status, created_at | `slot_number` UNIQUE, `status ∈ {AVAILABLE, OCCUPIED, RESERVED, OUT_OF_SERVICE}` |
| `vehicles` | id, plate_number, vehicle_type, created_at | `plate_number` UNIQUE, stored normalised |
| `parking_sessions` | id, vehicle_id, slot_id, entry_time, exit_time, duration_minutes, amount_paid, status, registered_by | FK → vehicles/slots/users `ON DELETE PROTECT`, `status ∈ {ACTIVE, COMPLETED}` |
| `payments` | id, parking_session_id, amount, payment_method, payment_status, paid_at, received_by | FK → session/users `ON DELETE PROTECT`, `payment_method ∈ {CASH, MPESA, CARD}` |

`ON DELETE PROTECT` on every foreign key is deliberate: financial and
occupancy history can never be orphaned by a cascade delete.

## REST API standards

All endpoints are versioned under `/api/v1/`:

```
GET  /api/v1/           service descriptor (implemented)
GET  /api/v1/slots      (Module 2/3)
GET  /api/v1/vehicles   (Module 3)
GET  /api/v1/sessions   (Module 4)
GET  /api/v1/payments   (Module 6)
```

Microservice endpoints (Flask):

```
POST /api/calculate-fee   → {"duration_minutes": 180, "fee": 100}
POST /api/barrier/open    → {"status": "success", "barrier": "opened"}
POST /api/barrier/close   → {"status": "success", "barrier": "closed"}
GET  /api/barrier/status  → simulated hardware state
```

## Security

- **CSRF** – Django middleware; every POST form carries `{% csrf_token %}` (verified: token-less POST → 403)
- **Password hashing** – Django's PBKDF2 (never plain text; unit-tested)
- **Role-based access control** – `admin_required` / `attendant_required` decorators + hidden UI affordances
- **Input validation** – forms, `get_json(silent=True)` + explicit 400s in Flask
- **SQL injection** – ORM parameterisation everywhere
- **Session management** – signed, HttpOnly session cookies; login required by default

## Design system

Brand: `#1565C0` primary · `#0D47A1` secondary · `#FFFFFF` / `#F5F7FA` /
`#E5E7EB` / `#1F2937` neutrals.

Rules enforced in `static/css/smartpark.css` and verified by test: **no color
gradients, no neon, no glassmorphism, no excessive shadows, no flashy
animation** (transitions disabled under `prefers-reduced-motion`). Flat
modern cards with a 1px border and a soft 2px-equivalent shadow, in the
Stripe/Linear/Supabase idiom.

## Module status

| Module | Status |
| --- | --- |
| 1 Authentication (login, logout, password reset, roles) | ✅ done |
| 2 Slot management (CRUD, status, live counts) | ✅ done |
| 3 Vehicle entry | ✅ done – form + `register_entry` service (allocation, duplicates, full lot) |
| 4 Vehicle exit | ✅ done – search, live fee quote, `register_exit` |
| 5 Fee calculation (Flask) | ✅ done – all 5 brackets verified |
| 6 Payment management | ✅ done – exit flow creates Payment (method, status, received_by) |
| 7 Barrier control (Flask) | ✅ done – simulated open/close/status (opens on payment, entry) |
| 8 Dashboard | ✅ done – stat cards + 7-day entries/exits/revenue trend chart |
| 9 Reports | ✅ done – admin KPIs, 14-day revenue, occupancy, CSV session export |
| 10 Public availability display (`/display`) | ✅ done – counters + slot map, 10 s auto refresh, no login |
| Supabase integration | ✅ done – Session pooler (IPv4), migrations applied, demo data seeded |
| Docker | ✅ done – one image, three services (`docker/docker-compose.yml`) |
| Tests (unit, Django↔Flask) | ✅ 70 passing (unit + live-service E2E lifecycle) |

Use cases and their module/code/test mapping → `USE_CASES.md`.
Algorithms (fee brackets, slot allocation, plate normalisation, atomic exit)
→ the [Algorithms](#algorithms) section above.
