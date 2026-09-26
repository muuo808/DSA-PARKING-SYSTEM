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
| 7 Barrier control (Flask) | ✅ simulated open/close/status (called on entry + exit) |
| 8 Dashboard | ✅ done – stat cards + 7-day entries/exits/revenue trend chart |
| 9 Reports | ✅ done – admin KPIs, 14-day revenue, occupancy, CSV session export |
| 10 Public availability display (`/display`) | ✅ done – 10s auto refresh |
| Supabase integration | ✅ done – Session pooler (IPv4), migrations applied, demo data seeded |
| Docker | ✅ done – one image, three services (`docker/docker-compose.yml`) |
| Tests (unit, Django↔Flask) | ✅ 60 passing (unit + live-service E2E lifecycle) |
