# AUTO-PARK

Modern web-based parking management system built with **Django** (core
business system) and **Flask** (fee + barrier microservices), backed by
**Supabase PostgreSQL**.

Full design and module documentation lives in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

**Prerequisites:** Python 3.11+ and pip. No database account, no `.env` and no
configuration are required to run it — the system falls back to a local
SQLite file until you point it at Supabase.

```bash
git clone https://github.com/muuo808/DSA-PARKING-SYSTEM.git
cd DSA-PARKING-SYSTEM

# 1. Virtual environment + dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Create the tables and the demo data (users + 12 slots)
python manage.py migrate
python manage.py seed_demo

# 3. Run everything (Django :8000, fee :5000, barrier :5001)
./run_dev.sh
```

Open http://127.0.0.1:8000 and sign in with a demo account below.
Public slot display (no login): http://127.0.0.1:8000/display

### Optional — use Supabase PostgreSQL

```bash
cp .env.example .env     # paste your DATABASE_URL (and a secret key)
python manage.py migrate # apply the schema to Supabase instead
python manage.py seed_demo
```

### Demo accounts

Created by `python manage.py seed_demo` (run it again with
`--reset-passwords` if you ever want the documented passwords back).

| Username | Password | Role | Access |
| --- | --- | --- | --- |
| `admin` | `fJvUta2d9b13` | Admin (+ superuser) | Everything: slots, users, `/admin/`, reports |
| `attendant` | `attendant123` | Attendant | Entry, exit, payments, dashboard — no slot/user admin |

> Change these before anything real is deployed.

### Roles in one line

* **Attendant** signs vehicles in/out and takes payments. Admin-only screens
  answer with an explicit **`403 — your role does not permit this action.`**
  (they are redirected to login only when signed out).
* **Admin** additionally manages slots/users and can use Django admin at
  `/admin/` (it is a superuser, so every model is visible and editable).

## Project structure

```
autopark/
├── manage.py
├── django_app/                 # Django project + applications
│   ├── settings.py             # env-driven config (DATABASE_URL, secrets)
│   ├── urls.py                 # root routing, /api/v1/ included
│   ├── accounts/               # Module 1: custom User, roles, auth, RBAC decorators
│   ├── parking/                # Modules 2-4: slots, vehicles, sessions + services/
│   ├── payments/               # Module 6: payment records
│   ├── reports/                # Module 9: KPIs, revenue trend, CSV export
│   ├── dashboard/              # Module 8 cards + Module 10 public /display
│   └── api/                    # API layer (/api/v1/)
├── flask_services/
│   ├── fee_service/            # Module 5: POST /api/calculate-fee
│   └── barrier_service/        # Module 7: /api/barrier/open|close|status
├── templates/                  # Django templates (Bootstrap 5)
├── static/css/autopark.css    # Design system - flat UI, brand palette
├── static/vendor/              # Bootstrap 5, Chart.js (vendored, offline)
├── tests/                      # Unit tests (Django + Flask)
├── docs/                       # DESIGN.md, USE_CASES.md, ARCHITECTURE.md
├── docker/                     # Dockerfile + compose (web + fee + barrier)
├── run_dev.sh                  # Starts all three services
├── requirements.txt
└── .env.example                # Configuration template
```

## Commands

| Task | Command |
| --- | --- |
| Start all services | `./run_dev.sh` |
| Start everything with Docker | `docker compose -f docker/docker-compose.yml up --build` |
| Run all tests | `python manage.py test tests` |
| Create migrations | `python manage.py makemigrations` |
| Apply migrations | `python manage.py migrate` |
| Seed demo slots | `python manage.py seed_slots --count 12 --prefix A` |
| Seed demo users + slots (fresh clone) | `python manage.py seed_demo` |
| Django admin | http://127.0.0.1:8000/admin/ |
| System check | `python manage.py check` |

## Key URLs

| URL | Purpose |
| --- | --- |
| `/` | Dashboard + 7-day trend chart (login required) |
| `/parking/` | Parking slot management |
| `/parking/entry/` | Register vehicle entry |
| `/parking/exit/` | Search plate, quote fee, take payment |
| `/reports/` | Module 9: KPIs, 14-day revenue, occupancy, session ledger (admin) |
| `/reports/export/` | Session ledger CSV download (admin) |
| `/display/` | Public slot map + counters for drivers, no login (auto-refresh 10s) |
| `/accounts/login/` | Sign in |
| `/admin/` | Django admin |
| `/api/v1/` | API descriptor (public) |
| `/api/v1/slots/`, `/vehicles/`, `/sessions/`, `/payments/` | Read-only JSON resources (staff login required) |
| `:5000/api/calculate-fee` | Flask fee service |
| `:5001/api/barrier/open` | Flask barrier service |

## Documentation

| Document | Contents |
| --- | --- |
| `docs/CRITICAL_ANALYSIS.md` | **Critical reading of the client's ToR** — requirements table, the 10 ambiguities the brief leaves open and how each was resolved, requirement → module mapping, honest limitations |
| `docs/USE_CASES.md` | Actors, 10 use cases (UC-01 … UC-10) with flows, each mapped to its module, code path and tests |
| `docs/DESIGN.md` | **(a)** algorithm per module · **(b)** data structures + why each was chosen · **(c)** dynamic database design (ER, integrity guarantees, runtime evolution) |
| `docs/ARCHITECTURE.md` | Stack, database schema + ER diagram, **algorithms** (fee brackets, slot allocation, plate normalisation, atomic exit), REST standards, security, module status |

## Testing

```bash
python manage.py test tests
```

Zero-config and offline: even when `.env` points at Supabase, the suite runs
against an in-memory SQLite test database (about 2½ minutes), so it can never
write to the live data and a fresh clone needs no database account.

To run the same suite against PostgreSQL instead — which also exercises the
pooler-safe teardown in `tests/runner.py` — opt in explicitly:

```bash
TEST_USE_POSTGRES=1 python manage.py test tests   # needs a role with CREATEDB
```

79 tests covering: fee calculation (all 5 charge brackets + boundaries),
plate normalisation, slot allocation, occupancy counts, vehicle/session rules,
payment status, role flags, password hashing, barrier simulation, the Flask
HTTP contracts, full entry -> exit -> payment lifecycle flows, report
aggregations (revenue/occupancy KPIs), the CSV session export, RBAC on the
reports screens, the 7-day dashboard trend series, the public display
(anonymous access, slot map states, order, counts, auto refresh) and the
`/api/v1/` JSON resources (descriptor discovery, auth, payload shape).

## Database

All records live in **Supabase PostgreSQL** (single source of truth) —
`DATABASE_URL` in `.env` is wired up and migrations are applied. Setting
`DATABASE_URL` empty falls back to a local SQLite file so the app still runs
offline.

> **IPv4 vs IPv6:** Supabase's dedicated host `db.<ref>.supabase.co` is
> **IPv6-only**. On a machine without IPv6 (this one) connection fails with
> *Network is unreachable* — use the **Session pooler** host
> `aws-N-<region>.pooler.supabase.com:5432` instead (Settings → Database →
> Connection pooler → Session). That is what `.env` uses.

Schema: `python manage.py migrate` (applied). Tests default to an in-memory
SQLite database (no server needed); with `TEST_USE_POSTGRES=1` they
create/drop their own `test_postgres` database on the same server, so that
path needs a role with `CREATEDB` (the `postgres` role qualifies).
