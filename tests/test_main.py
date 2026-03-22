from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ss_notifier.config import Config, DealType
from ss_notifier.main import main, passes_filters, run_once, run_seed
from ss_notifier.scraper import Listing


def _listing(**kwargs: object) -> Listing:
    defaults: dict[str, object] = {
        "listing_id": "id1",
        "url": "https://example.com/1",
        "title": "Nice flat",
        "street": "Main",
        "rooms": "2",
        "area_m2": "50",
        "floor": "3",
        "series": "brick",
        "price_raw": "50 000 €",
        "price_eur": 50_000.0,
        "is_rent": None,
    }
    defaults.update(kwargs)
    return Listing(**defaults)


def _config(state_db: Path, **kwargs: object) -> Config:
    base: dict[str, object] = {
        "ss_listing_url": "https://example.com/list/",
        "price_min_eur": 10000,
        "price_max_eur": 200000,
        "deal_type": DealType.all,
        "telegram_bot_token": "token",
        "telegram_chat_id": "123",
        "libsql_url": "",
        "state_db_path": state_db,
        "dry_run": False,
        "max_pages": 1,
        "request_timeout_sec": 30.0,
        "delay_between_pages_sec": 1.5,
    }
    base.update(kwargs)
    return Config(**base)


class TestPassesFilters:
    def test_rejects_missing_price(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path / "s.sqlite")
        li = _listing(price_eur=None)
        assert passes_filters(li, cfg) is False

    def test_rent_mode_requires_is_rent_true(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path / "s.sqlite", deal_type=DealType.rent)
        assert passes_filters(_listing(price_eur=50000, is_rent=True), cfg) is True
        assert passes_filters(_listing(price_eur=50000, is_rent=False), cfg) is False
        assert passes_filters(_listing(price_eur=50000, is_rent=None), cfg) is False

    def test_sale_mode_requires_is_rent_false(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path / "s.sqlite", deal_type=DealType.sale)
        assert passes_filters(_listing(price_eur=50000, is_rent=False), cfg) is True
        assert passes_filters(_listing(price_eur=50000, is_rent=True), cfg) is False
        assert passes_filters(_listing(price_eur=50000, is_rent=None), cfg) is False

    def test_all_mode_ignores_is_rent(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path / "s.sqlite", deal_type=DealType.all)
        for rent in (True, False, None):
            assert passes_filters(_listing(price_eur=50000, is_rent=rent), cfg) is True

    def test_price_bounds(self, tmp_path: Path) -> None:
        cfg = _config(tmp_path / "s.sqlite", price_min_eur=40000, price_max_eur=60000)
        assert passes_filters(_listing(price_eur=39999), cfg) is False
        assert passes_filters(_listing(price_eur=40000), cfg) is True
        assert passes_filters(_listing(price_eur=60000), cfg) is True
        assert passes_filters(_listing(price_eur=60001), cfg) is False


class TestRunSeed:
    def test_calls_seed_with_matching_ids(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db)
        rows = [
            _listing(listing_id="a", price_eur=50000),
            _listing(listing_id="b", price_eur=5),
        ]
        with (
            patch("ss_notifier.main.fetch_listings", return_value=rows) as fl,
            patch("ss_notifier.main.seed_ids", return_value=2) as seed,
        ):
            n = run_seed(cfg)
        assert n == 2
        fl.assert_called_once_with(cfg)
        seed.assert_called_once_with(cfg, ["a"])


class TestRunOnce:
    def test_dry_run_skips_telegram_and_db(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db, dry_run=True)
        rows = [_listing(listing_id="x", price_eur=50000)]
        with (
            patch("ss_notifier.main.fetch_listings", return_value=rows),
            patch("ss_notifier.main.is_known", return_value=False) as known,
            patch("ss_notifier.main.send_telegram_listing") as send,
            patch("ss_notifier.main.insert_seen") as ins,
        ):
            n = run_once(cfg)
        assert n == 0
        known.assert_called_once_with(cfg, "x")
        send.assert_not_called()
        ins.assert_not_called()

    def test_sends_and_inserts_for_new_listing(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db)
        rows = [_listing(listing_id="new1", price_eur=50000)]
        with (
            patch("ss_notifier.main.fetch_listings", return_value=rows),
            patch("ss_notifier.main.is_known", return_value=False),
            patch("ss_notifier.main.send_telegram_listing") as send,
            patch("ss_notifier.main.insert_seen") as ins,
        ):
            n = run_once(cfg)
        assert n == 1
        send.assert_called_once()
        ins.assert_called_once_with(cfg, "new1", notified=True)

    def test_skips_known_ids(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db)
        rows = [_listing(listing_id="old", price_eur=50000)]
        with (
            patch("ss_notifier.main.fetch_listings", return_value=rows),
            patch("ss_notifier.main.is_known", return_value=True),
            patch("ss_notifier.main.send_telegram_listing") as send,
        ):
            n = run_once(cfg)
        assert n == 0
        send.assert_not_called()

    def test_validate_telegram_when_not_dry_run(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db, telegram_bot_token="", telegram_chat_id="")
        with (
            patch("ss_notifier.main.fetch_listings", return_value=[]),
            pytest.raises(ValueError, match="telegram"),
        ):
            run_once(cfg)


class TestMain:
    def test_invokes_run_once_with_loaded_config(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db)
        with (
            patch("ss_notifier.main.load_config", return_value=cfg),
            patch("ss_notifier.main.run_once", return_value=3) as ro,
        ):
            main(["--config", str(tmp_path / "c.yaml")])
        ro.assert_called_once()
        assert ro.call_args[0][0].dry_run is False

    def test_dry_run_flag_sets_config(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db, dry_run=False)
        with (
            patch("ss_notifier.main.load_config", return_value=cfg),
            patch("ss_notifier.main.run_once") as ro,
        ):
            main(["--config", str(tmp_path / "c.yaml"), "--dry-run"])
        assert ro.call_args[0][0].dry_run is True

    def test_exits_on_run_failure(self, tmp_path: Path) -> None:
        db = tmp_path / "state.sqlite"
        cfg = _config(db)
        with (
            patch("ss_notifier.main.load_config", return_value=cfg),
            patch("ss_notifier.main.run_once", side_effect=RuntimeError("network")),
            patch("ss_notifier.main.sys.exit") as ex,
        ):
            main(["--config", str(tmp_path / "c.yaml")])
        ex.assert_called_once_with(1)
