from __future__ import annotations

from pathlib import Path

from ss_notifier.config import Config, DealType
from ss_notifier.store import insert_seen, is_known, seed_ids


def _cfg(db: Path) -> Config:
    return Config(
        ss_listing_url="https://example.com/",
        price_min_eur=0,
        price_max_eur=1,
        deal_type=DealType.all,
        telegram_bot_token="t",
        telegram_chat_id="1",
        libsql_url="",
        state_db_path=db,
        dry_run=False,
        max_pages=1,
        request_timeout_sec=30.0,
        delay_between_pages_sec=1.0,
    )


def test_sqlite_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    cfg = _cfg(db)
    assert is_known(cfg, "a") is False
    insert_seen(cfg, "a", notified=True)
    assert is_known(cfg, "a") is True


def test_seed_ids(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    cfg = _cfg(db)
    n = seed_ids(cfg, ["x", "y"])
    assert n == 2
    assert is_known(cfg, "x") and is_known(cfg, "y")
