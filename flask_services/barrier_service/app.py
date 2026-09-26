"""
SmartPark Kenya – Barrier Control Service (Flask microservice).

Module 7 endpoints (hardware simulated for now):

    POST /api/barrier/open   -> {"status": "success", "barrier": "opened"}
    POST /api/barrier/close  -> {"status": "success", "barrier": "closed"}

The simulation keeps barrier state in memory and logs every command with a
timestamp, standing in for the GPIO/serial call a real boom barrier would
receive. Future IoT integration replaces ``_actuate()`` only.

Run:  python flask_services/barrier_service/app.py   (port 5001)
"""

import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

# Simulated hardware state: "closed" | "open"
_barrier_state = "closed"
_command_log: list[dict[str, str]] = []


def _actuate(command: str) -> str:
    """
    Simulate sending a command to the physical barrier.

    Replace this function when wiring real hardware (relay/GPIO/serial).
    """
    global _barrier_state
    _barrier_state = "open" if command == "open" else "closed"
    return _barrier_state


def _record(command: str) -> None:
    _command_log.append(
        {
            "command": command,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    del _command_log[:-100]  # keep the last 100 commands only


def open_barrier() -> dict[str, str]:
    """Open the barrier (entry/exit gate)."""
    state = _actuate("open")
    _record("open")
    return {"status": "success", "barrier": "opened" if state == "open" else state}


def close_barrier() -> dict[str, str]:
    """Close the barrier after the vehicle has passed."""
    state = _actuate("close")
    _record("close")
    return {"status": "success", "barrier": "closed" if state == "closed" else state}


@app.get("/api/health")
def health():
    return jsonify({"service": "barrier-service", "status": "ok"})


@app.get("/api/barrier/status")
def barrier_status():
    """Current simulated barrier state (useful for the entry/exit screens)."""
    return jsonify(
        {
            "barrier": _barrier_state,
            "last_command": _command_log[-1] if _command_log else None,
            "total_commands": len(_command_log),
        }
    )


@app.post("/api/barrier/open")
def open_endpoint():
    return jsonify(open_barrier())


@app.post("/api/barrier/close")
def close_endpoint():
    return jsonify(close_barrier())


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "not_found"}), 404


if __name__ == "__main__":
    # FLASK_HOST=0.0.0.0 inside Docker so the service is reachable from
    # other containers; defaults to loopback for local development.
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("BARRIER_SERVICE_PORT", 5001)),
    )
