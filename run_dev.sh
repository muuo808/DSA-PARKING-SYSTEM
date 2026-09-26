#!/usr/bin/env bash
# Start every SmartPark Kenya service:
#   Django core app   -> http://127.0.0.1:8000
#   Flask fee service -> http://127.0.0.1:5000   (Module 5)
#   Flask barrier     -> http://127.0.0.1:5001   (Module 7)
#
# Usage:  ./run_dev.sh        (stop everything with Ctrl+C)

set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "Virtual environment missing. Create it first:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

PIDS=()
cleanup() {
  echo ""
  echo "Stopping SmartPark services..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

echo "Starting Django (core) on http://127.0.0.1:8000 ..."
"$PY" manage.py runserver 127.0.0.1:8000 &
PIDS+=($!)

echo "Starting Flask fee service on http://127.0.0.1:5000 ..."
"$PY" flask_services/fee_service/app.py &
PIDS+=($!)

echo "Starting Flask barrier service on http://127.0.0.1:5001 ..."
"$PY" flask_services/barrier_service/app.py &
PIDS+=($!)

sleep 2
cat <<'EOF'

  SmartPark Kenya is running:
    Site + admin : http://127.0.0.1:8000
    Public display (Module 10): http://127.0.0.1:8000/display
    Fee service  : http://127.0.0.1:5000/api/calculate-fee
    Barrier      : http://127.0.0.1:5001/api/barrier/open

  Press Ctrl+C to stop all services.

EOF

wait
