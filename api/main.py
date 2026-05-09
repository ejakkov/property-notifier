from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ss_notifier.config import load_config
from ss_notifier.main import run_once
from ss_notifier.store import delete_seen_older_than

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

LOGGER = logging.getLogger(__name__)

STALE_DAYS = 3

app = FastAPI()


def load_cfg():
    cfg_yaml = os.environ.get("CONFIG_YAML", "").strip()

    if not cfg_yaml:
        raise HTTPException(
            status_code=500,
            detail="CONFIG_YAML not set",
        )

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
        return cfg
    finally:
        try:
            os.unlink(path)
        except OSError:
            LOGGER.warning("Temporary config cleanup failed: path=%s", path)


@app.get("/")
async def root():
    return {"ok": True}


@app.get("/api/main")
@app.post("/api/main")
async def run_notifier():
    LOGGER.info("Notifier request received")

    try:
        cfg = load_cfg()
        n_sent = run_once(cfg)

        LOGGER.info("Notifier request completed: n_sent=%s", n_sent)

        return {
            "ok": True,
            "n_sent": n_sent,
        }

    except Exception as e:
        LOGGER.exception("Notifier run failed")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


@app.get("/api/prune_seen")
@app.post("/api/prune_seen")
async def prune_seen():
    LOGGER.info("Prune request received")

    try:
        cfg = load_cfg()

        cfg.validate_turso()

        n_deleted = delete_seen_older_than(
            cfg,
            days=STALE_DAYS,
        )

        LOGGER.info(
            "Prune request completed: n_deleted=%s older_than_days=%s",
            n_deleted,
            STALE_DAYS,
        )

        return {
            "ok": True,
            "n_deleted": n_deleted,
            "older_than_days": STALE_DAYS,
        }

    except Exception as e:
        LOGGER.exception("Prune run failed")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )