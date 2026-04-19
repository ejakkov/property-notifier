from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ss_notifier.config import Config


def _connect_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def _connect_libsql(url: str) -> object:
    import libsql

    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    return libsql.connect(url, auth_token=token)


def _ensure_schema(conn: object) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_listings (
            listing_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            notified_at TEXT
        )
        """
    )
    conn.commit()


@contextmanager
def _connection(cfg: Config) -> Iterator[object]:
    if cfg.uses_remote():
        conn = _connect_libsql(cfg.libsql_url)
        try:
            _ensure_schema(conn)
            yield conn
        finally:
            conn.close()
    else:
        conn = _connect_sqlite(cfg.state_db_path)
        try:
            _ensure_schema(conn)
            yield conn
        finally:
            conn.close()


def is_known(cfg: Config, listing_id: str) -> bool:
    with _connection(cfg) as conn:
        row = conn.execute("SELECT 1 FROM seen_listings WHERE listing_id = ?", (listing_id,)).fetchone()

        return row is not None


def insert_seen(cfg: Config, listing_id: str, *, notified: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connection(cfg) as conn:
        conn.execute(
            """
            INSERT INTO seen_listings (listing_id, first_seen_at, notified_at)
            VALUES (?, ?, ?)
            """,
            (listing_id, now, now if notified else None),
        )
        conn.commit()


def seed_ids(cfg: Config, ids: Iterable[str]) -> int:
    "Mark all given listing IDs as seen without notifying."
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    with _connection(cfg) as conn:
        for id in ids:
            conn.execute(
                "INSERT INTO seen_listings (listing_id, first_seen_at, notified_at) VALUES (?, ?, ?)",
                (id, now, None),
            )
            n += 1
        conn.commit()
    return n


def delete_seen_older_than(cfg: Config, *, days: int) -> int:
    """Remove seen_listings rows whose first_seen_at is strictly older than *days*"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connection(cfg) as conn:
        cur = conn.execute(
            "DELETE FROM seen_listings WHERE DATE(first_seen_at) < ?",
            (cutoff,),
        )
        conn.commit()
        rc = getattr(cur, "rowcount", -1)
        return int(rc) if rc is not None and rc >= 0 else 0
