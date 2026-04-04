from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ss_notifier.config import Config

logger = logging.getLogger(__name__)


def parse_listing_floor(floor_cell: str) -> int | None:
    """Apartment level from the listing cell, e.g. ``3/9`` → 3."""
    s = " ".join(floor_cell.split())
    if not s:
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    return int(m.group(0))


@dataclass(frozen=True)
class Listing:
    """One row from the SS.com listing table."""

    listing_id: str
    url: str
    title: str
    street: str
    rooms: str
    area_m2: str
    floor: str
    series: str
    price_raw: str
    price_eur: float | None
    is_rent: bool | None


def _normalize_lv_price_number(raw: str) -> float | None:
    """Parse a EUR amount from SS.com-style cells (mixed thousand/decimal separators)."""
    # Replace non-breaking spaces with spaces and remove extra spaces
    s = raw.replace("\xa0", " ").strip()

    # Remove extra spaces within the string
    s = re.sub(r"\s+", "", s)

    if not s:
        logger.warning("Listing row %s: skip — no price number in the cell", raw)
        return None
    if re.fullmatch(r"\d+", s):
        return float(s)
    if "," in s and "." in s:
        # 1.234,56 or 1,234.56
        if s.rfind(".") > s.rfind(","):
            return float(s.replace(",", ""))
        return float(s.replace(".", "").replace(",", "."))
    if "," in s:
        # 157,000
        parts = s.split(",")
        return float("".join(parts))
    if "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2 and parts[1].isdigit():
            return float(f"{parts[0]}.{parts[1]}")

    logger.warning("Listing row %s: skip — no price number in the cell", raw)
    return None


def parse_price_cell(price_cell_text: str) -> tuple[float | None, bool | None]:
    """
    Parse main price column. Returns (amount, is_rent).
    is_rent True for monthly rent, False for sale lump sum, None if unknown / not a price.
    """
    t = " ".join(price_cell_text.split())
    tl = t.lower()
    if not t or not re.search(r"\d", t):
        return None, None
    if "pērku" in tl and "€" not in t:
        return None, None
    is_rent = "mēn" in tl
    # Extract the numeric chunk before €
    m = re.search(r"([\d\s\.,]+)\s*€", t)
    if not m:
        return None, None
    amount = _normalize_lv_price_number(m.group(1))
    if amount is None:
        return None, None
    if is_rent:
        return amount, True
    return amount, False


def listing_slug_from_href(href: str) -> str | None:
    path = urlparse(href).path.rstrip("/")
    if not path.endswith(".html"):
        return None
    base = path.rsplit("/", 1)[-1]
    if base.endswith(".html"):
        return base[: -len(".html")]
    return None


def parse_listing_html(html: str, base_url: str = "https://www.ss.com/") -> list[Listing]:
    """Parse SS.com category listing HTML into structured rows."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    for tr in soup.find_all("tr"):
        tid = tr.get("id") or ""

        # Skip non-listing rows
        if not tid.startswith("tr_") or not tid[3:].isdigit():
            continue


        tds = tr.find_all("td")

        # Find the link to the listing
        link = None
        for a in tds[2].find_all("a", href=True):
            h = str(a.get("href", ""))
            if "/msg/" in h and h.endswith(".html"):
                link = a
                break
        if not link:
            logger.warning("Listing row %s: skip — no /msg/...html link in title cell", tid)
            continue
        href = str(link.get("href", "")).strip()


        slug = listing_slug_from_href(href)
        if not slug:
            continue

        title = link.get_text(" ", strip=True)
        street = tds[3].get_text(" ", strip=True)
        rooms = tds[4].get_text(" ", strip=True)
        area_m2 = tds[5].get_text(" ", strip=True)
        floor = tds[6].get_text(" ", strip=True)
        series = tds[7].get_text(" ", strip=True)
        price_raw = tds[9].get_text(" ", strip=True)
        price_eur, is_rent = parse_price_cell(price_raw)
        abs_url = urljoin(base_url, href)
        out.append(
            Listing(
                listing_id=slug,
                url=abs_url,
                title=title,
                street=street,
                rooms=rooms,
                area_m2=area_m2,
                floor=floor,
                series=series,
                price_raw=price_raw,
                price_eur=price_eur,
                is_rent=is_rent,
            )
        )
    return out


def paginate_urls(listing_url: str, max_pages: int) -> list[str]:
    """First page is listing_url; further pages are pageN.html in the same directory."""
    base = listing_url.rstrip("/") + "/"
    urls = [base]
    for n in range(2, max_pages + 1):
        urls.append(urljoin(base, f"page{n}.html"))
    return urls


def fetch_listings(config: Config) -> list[Listing]:
    """HTTP GET listing pages and parse all rows."""
    all_rows = []
    with httpx.Client(timeout=config.request_timeout_sec) as client:
        for listing_url in config.ss_listing_urls:
            urls = paginate_urls(listing_url, config.max_pages)
            for i, url in enumerate(urls):
                resp = client.get(url)
                resp.raise_for_status()
                all_rows.extend(parse_listing_html(resp.text, base_url="https://www.ss.com/"))
                if i + 1 < len(urls):
                    time.sleep(config.delay_between_pages_sec)
    return all_rows
