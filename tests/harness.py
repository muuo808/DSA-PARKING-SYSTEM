"""Test harness: run the real Flask services on ephemeral ports."""

import importlib.util
import threading
from pathlib import Path
from typing import Any

from werkzeug.serving import make_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_flask_service(module_name: str, relative_path: str) -> Any:
    """Import a Flask app module directly from its file path."""
    path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiveService:
    """
    Runs a Flask app on 127.0.0.1:<ephemeral port> for the duration of a test.

    Usage::

        cls.fee = LiveService("flask_services/fee_service/app.py")
        cls.fee.start()          # -> base_url like http://127.0.0.1:54321
        ...
        cls.fee.stop()
    """

    def __init__(self, relative_path: str) -> None:
        self.module = load_flask_service(
            f"live_{Path(relative_path).stem}_{id(self)}", relative_path
        )
        self.server = make_server("127.0.0.1", 0, self.module.app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def start(self) -> "LiveService":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
