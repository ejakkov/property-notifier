from __future__ import annotations

from pathlib import Path

import pytest

from ss_notifier.config import load_config, resolve_env


def test_resolve_env_substitutes() -> None:
    import os

    os.environ["MY_TEST_VAR"] = "hello"
    try:
        assert resolve_env("pre-${MY_TEST_VAR}-post") == "pre-hello-post"
    finally:
        del os.environ["MY_TEST_VAR"]


def test_resolve_env_missing_is_empty() -> None:
    import os

    key = "VAR_THAT_SHOULD_NOT_EXIST_12345"
    os.environ.pop(key, None)
    assert resolve_env("x-${VAR_THAT_SHOULD_NOT_EXIST_12345}-y") == "x--y"


def test_load_config_interpolates_and_telegram_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-env-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "from-env-chat")
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        """
ss_listing_url: "https://example.com/"
price_min_eur: 1
price_max_eur: 2
deal_type: all
telegram_bot_token: ""
telegram_chat_id: ""
libsql_url: ""
state_db_path: state.sqlite
dry_run: false
max_pages: 1
request_timeout_sec: 30
delay_between_pages_sec: 1
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.telegram_bot_token == "from-env-token"
    assert cfg.telegram_chat_id == "from-env-chat"


def test_load_config_libsql_requires_turso_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        """
ss_listing_url: "https://example.com/"
libsql_url: "libsql://db.turso.io"
telegram_bot_token: "t"
telegram_chat_id: "c"
state_db_path: state.sqlite
dry_run: false
max_pages: 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="TURSO_AUTH_TOKEN"):
        load_config(cfg_file)


def test_load_config_libsql_ok_with_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok")
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        """
ss_listing_url: "https://example.com/"
libsql_url: "libsql://db.turso.io"
telegram_bot_token: "t"
telegram_chat_id: "c"
state_db_path: state.sqlite
dry_run: false
max_pages: 1
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.libsql_url == "libsql://db.turso.io"
    assert cfg.uses_remote()
