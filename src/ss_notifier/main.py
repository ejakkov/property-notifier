from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from ss_notifier.config import Config, DealType, load_config
from ss_notifier.notify import send_telegram_listing
from ss_notifier.scraper import Listing, fetch_listings
from ss_notifier.store import insert_seen, is_known, seed_ids

logger = logging.getLogger(__name__)


def passes_filters(listing: Listing, cfg: Config) -> bool:
    if listing.price_eur is None:
        return False
    if cfg.deal_type == DealType.rent:
        if listing.is_rent is not True:
            return False
    elif cfg.deal_type == DealType.sale:
        if listing.is_rent is not False:
            return False
    return cfg.price_min_eur <= listing.price_eur <= cfg.price_max_eur


def run_seed(cfg: Config) -> int:
    listings = fetch_listings(cfg)
    matching = [x for x in listings if passes_filters(x, cfg)]
    ids = [x.listing_id for x in matching]
    n = seed_ids(cfg, ids)
    logger.info("Seed: %d listings matched filters, %d new IDs recorded (no Telegram)", len(matching), n)
    return n

def run_once(cfg: Config) -> int:
    if not cfg.dry_run:
        cfg.validate_telegram()

    listings = fetch_listings(cfg)
    matching = [x for x in listings if passes_filters(x, cfg)]
    logger.info("Fetched %d rows, %d match filters", len(listings), len(matching))
    n_sent = 0
    for listing in matching:
        if is_known(cfg, listing.listing_id):
            continue
        if cfg.dry_run:
            logger.info(
                "[dry-run] would notify: %s | %s | %s",
                listing.listing_id,
                listing.title[:80],
                listing.price_raw,
            )
            continue
        send_telegram_listing(
            listing,
            bot_token=cfg.telegram_bot_token,
            chat_id=cfg.telegram_chat_id,
            timeout_sec=cfg.request_timeout_sec,
        )
        insert_seen(cfg, listing.listing_id, notified=True)
        n_sent += 1
        logger.info("Notified: %s", listing.listing_id)
    return n_sent


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions only; do not write DB or call Telegram",
    )
    p.add_argument(
        "--seed",
        action="store_true",
        help="Record all currently matching listing IDs without sending Telegram",
    )
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.dry_run:
        cfg = replace(cfg, dry_run=True)
    try:
        n = run_once(cfg)
        logger.info("Done. New notifications sent: %d", n)
    except Exception as e:
        logger.exception("Run failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
