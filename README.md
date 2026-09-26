# SmartPark Kenya

Modern web-based parking management system built with **Django** (core
business system) and **Flask** (fee + barrier microservices), backed by
**Supabase PostgreSQL**.

Full design and module documentation lives in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start

```bash
cd "Desktop/Y2SEM1/DSA PARKING SYST"

# 1. Environment (already created)
source .venv/bin/activate

# 2. Configure the database (Supabase URI) - optional for local bootstrap
cp .env.example .env        # then edit DATABASE_URL

# 3. Run everything (Django :8000, fee :5000, barrier :5001)
./run_dev.sh
```

Open http://127.0.0.1:8000 and sign in.

### Demo accounts

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
smartpark/
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
├── static/css/smartpark.css    # Design system - flat UI, brand palette
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
| `/api/v1/` | API descriptor |
| `:5000/api/calculate-fee` | Flask fee service |
| `:5001/api/barrier/open` | Flask barrier service |

## Documentation

| Document | Contents |
| --- | --- |
| `docs/USE_CASES.md` | Actors, 10 use cases (UC-01 … UC-10) with flows, each mapped to its module, code path and tests |
| `docs/DESIGN.md` | **(a)** algorithm per module · **(b)** data structures + why each was chosen · **(c)** dynamic database design (ER, integrity guarantees, runtime evolution) |
| `docs/ARCHITECTURE.md` | Stack, database schema + ER diagram, **algorithms** (fee brackets, slot allocation, plate normalisation, atomic exit), REST standards, security, module status |

## Testing

```bash
python manage.py test tests
```

70 tests covering: fee calculation (all 5 charge brackets + boundaries),
plate normalisation, slot allocation, occupancy counts, vehicle/session rules,
payment status, role flags, password hashing, barrier simulation, the Flask
HTTP contracts, full entry -> exit -> payment lifecycle flows, report
aggregations (revenue/occupancy KPIs), the CSV session export, RBAC on the
reports screens, the 7-day dashboard trend series and the public display
(anonymous access, slot map states, order, counts, auto refresh).

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

Schema: `python manage.py migrate` (applied). Tests create/drop their own
`test_postgres` database on the same server, so the suite needs a role with
`CREATEDB` (the `postgres` role qualifies).
