from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class DealType(str, Enum):
    """Which listings to consider for price filtering."""

    all = "all"
    rent = "rent"
    sale = "sale"


_DEFAULTS: dict[str, Any] = {
    "ss_listing_urls": ["https://www.ss.com/lv/real-estate/flats/riga/centre/"],
    "price_min_eur": 0,
    "price_max_eur": 1000000,
    "floor_min": None,
    "floor_max": None,
    "deal_type": "all",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "libsql_url": "",
    "state_db_path": "data/state.sqlite",
    "dry_run": False,
    "max_pages": 1,
    "request_timeout_sec": 30.0,
    "delay_between_pages_sec": 1.5,
}


@dataclass(frozen=True)
class Config:
    """Runtime settings loaded from YAML (and optional env overrides)."""

    ss_listing_urls: list[str]
    price_min_eur: float
    price_max_eur: float
    floor_min: int | None
    floor_max: int | None
    deal_type: DealType
    telegram_bot_token: str
    telegram_chat_id: str
    libsql_url: str
    state_db_path: Path
    dry_run: bool
    max_pages: int
    request_timeout_sec: float
    delay_between_pages_sec: float

    def uses_remote(self) -> bool:
        return bool(self.libsql_url.strip())

    def validate_telegram(self) -> None:
        if not self.telegram_bot_token.strip() or not self.telegram_chat_id.strip():
            raise ValueError(
                "telegram_bot_token and telegram_chat_id are required in config (or via "
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env) unless dry_run is true"
            )

    def validate_turso(self) -> None:
        if not self.uses_remote():
            return
        if not os.environ.get("TURSO_AUTH_TOKEN", "").strip():
            raise ValueError("TURSO_AUTH_TOKEN is required in the environment when libsql_url is set")


def resolve_env(value: str) -> str:
    """Replace ${VAR_NAME} with environment variable values (empty string if unset)."""

    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def _resolve_env_in_values(obj: Any) -> Any:
    if isinstance(obj, str):
        return resolve_env(obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_in_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_in_values(x) for x in obj]
    return obj


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if v is not None:
            out[k] = v
    return out


def _optional_floor_bound(key: str, raw: Any) -> int | None:
    if raw is None:
        return None
    n = int(raw)
    if n < 0:
        raise ValueError(f"{key} must be null or a non-negative integer")
    return n


def _coerce_deal_type(raw: str) -> DealType:
    try:
        return DealType(str(raw).strip().lower())
    except ValueError as e:
        allowed = ", ".join(x.value for x in DealType)
        raise ValueError(f"deal_type must be one of: {allowed}") from e


def _coerce_listing_urls(data: dict[str, Any]) -> list[str]:
    urls_raw = data.get("ss_listing_urls")

    if urls_raw is None:
        urls_raw = _DEFAULTS["ss_listing_urls"]

    urls = [str(x).strip() for x in urls_raw]

    if not urls:
        raise ValueError("At least one listing URL must be provided in ss_listing_urls")
    return urls


def load_config(path: str | Path) -> Config:
    """Load configuration from a YAML file. Paths in the file are resolved relative to the file."""
    cfg_path = Path(path).expanduser().resolve()
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")

    data = _merge_dict(_DEFAULTS, raw)
    data = _resolve_env_in_values(data)

    token = str(data.get("telegram_bot_token") or "").strip()
    chat_id = str(data.get("telegram_chat_id") or "").strip()

    # Secrets may be supplied via environment when YAML leaves them empty
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not data.get("dry_run", False):
        if not token:
            raise ValueError("telegram_bot_token is required in config (or via TELEGRAM_BOT_TOKEN env)")
        if not chat_id:
            raise ValueError("telegram_chat_id is required in config (or via TELEGRAM_CHAT_ID env)")

    libsql_url = str(data.get("libsql_url") or "").strip()

    sdp = data.get("state_db_path", _DEFAULTS["state_db_path"])
    state_db_path = Path(sdp)
    if not state_db_path.is_absolute():
        state_db_path = (cfg_path.parent / state_db_path).resolve()

    max_pages = int(data["max_pages"])
    if max_pages < 1 or max_pages > 100:
        raise ValueError("max_pages must be between 1 and 100")

    price_min_eur = float(data["price_min_eur"])
    price_max_eur = float(data["price_max_eur"])

    floor_min = _optional_floor_bound("floor_min", data.get("floor_min"))
    floor_max = _optional_floor_bound("floor_max", data.get("floor_max"))
    if floor_min is not None and floor_max is not None and floor_min > floor_max:
        raise ValueError("floor_min cannot be greater than floor_max")

    cfg = Config(
        ss_listing_urls=_coerce_listing_urls(data),
        price_min_eur=price_min_eur,
        price_max_eur=price_max_eur,
        floor_min=floor_min,
        floor_max=floor_max,
        deal_type=_coerce_deal_type(str(data["deal_type"])),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        libsql_url=libsql_url,
        state_db_path=state_db_path,
        dry_run=bool(data["dry_run"]),
        max_pages=max_pages,
        request_timeout_sec=float(data["request_timeout_sec"]),
        delay_between_pages_sec=float(data["delay_between_pages_sec"]),
    )
    cfg.validate_turso()
    return cfg
