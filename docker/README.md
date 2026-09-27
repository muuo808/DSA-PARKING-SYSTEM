# AUTO-PARK — Docker

One image, three containers (mirrors `run_dev.sh`):

| Service | Container command | Host port |
| --- | --- | --- |
| `web` | `manage.py runserver 0.0.0.0:8000` | 8000 |
| `fee` | `flask_services/fee_service/app.py` | 5000 |
| `barrier` | `flask_services/barrier_service/app.py` | 5001 |

The database is **Supabase PostgreSQL** (external) — no database container is
started. `DATABASE_URL` and secrets come from the project-root `.env`
(excluded from the image by `.dockerignore`).

## Run

```bash
cd "Desktop/Y2SEM1/DSA PARKING SYST"
docker compose -f docker/docker-compose.yml up --build
```

Then open http://127.0.0.1:8000 and sign in.

Inside the network the web app talks to the Flask services by service name
(`http://fee:5000`, `http://barrier:5001`) — set in `docker-compose.yml`.

## Useful commands

```bash
docker compose -f docker/docker-compose.yml ps          # status
docker compose -f docker/docker-compose.yml logs -f web # Django logs
docker compose -f docker/docker-compose.yml down        # stop everything
```

## First run against a fresh database

```bash
docker compose -f docker/docker-compose.yml run --rm web \
  python manage.py migrate
docker compose -f docker/docker-compose.yml run --rm web \
  python manage.py seed_slots --count 12 --prefix A
```

> `runserver` is the development server — fine for demos and coursework.
> For a real deployment add gunicorn + whitenoise and set `DJANGO_DEBUG=false`.
