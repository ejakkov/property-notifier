from __future__ import annotations

import html
from urllib.parse import quote

import httpx

from ss_notifier.scraper import Listing


def _telegram_api_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{quote(bot_token, safe='')}/{method}"


def format_listing_message(listing: Listing) -> str:
    title = html.escape(listing.title)
    street = html.escape(listing.street)
    price = html.escape(listing.price_raw)
    parts = [
        "<b>New SS.com listing</b>",
        "",
        f"{title}",
        f"{street}",
        f"Price: {price}",
        f'<a href="{html.escape(listing.url, quote=True)}">Open on SS.com</a>',
    ]
    return "\n".join(parts)


def send_telegram_listing(
    listing: Listing,
    *,
    bot_token: str,
    chat_id: str,
    timeout_sec: float = 30.0,
) -> None:
    text = format_listing_message(listing)
    url = _telegram_api_url(bot_token, "sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    with httpx.Client(timeout=timeout_sec) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
