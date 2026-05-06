"""
Vercel Serverless Function: run the notifier on GET or POST /api/main.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

LOGGER = logging.getLogger(__name__)


def _json(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    data = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(data)


class handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        LOGGER.info("Notifier request received: method=%s path=%s", self.command, self.path)

        cfg_yaml = os.environ.get("CONFIG_YAML", "").strip()
        if not cfg_yaml:
            LOGGER.warning("Notifier request rejected: CONFIG_YAML not set")
            _json(self, 500, {"ok": False, "error": "CONFIG_YAML not set"})
            return

        from ss_notifier.config import load_config
        from ss_notifier.main import run_once

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(cfg_yaml)
            path = f.name
        try:
            cfg = load_config(path)
            n_sent = run_once(cfg)
        except Exception as e:
            LOGGER.exception("Notifier run failed")
            _json(self, 500, {"ok": False, "error": str(e)})
            return
        finally:
            try:
                os.unlink(path)
            except OSError:
                LOGGER.warning("Temporary config cleanup failed: path=%s", path)

        LOGGER.info("Notifier request completed: n_sent=%s", n_sent)
        _json(self, 200, {"ok": True, "n_sent": n_sent})
