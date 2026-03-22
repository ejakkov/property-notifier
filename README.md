# ss.com listing notifier

Small Python utility that watches a [ss.com](https://www.ss.com/) real-estate category page, applies price and deal-type filters, remembers listings it has already seen, and sends **Telegram** messages when new matching ads appear.

## What it does

- Fetches one or more paginated listing pages over HTTP and parses the HTML table (same structure as the site’s category views).
- Keeps durable state in **SQLite** so each listing is only treated as “new” once.
- Sends a short HTML-formatted Telegram message with title, address line, price text, and a link to the ad.

## Setup

1. Clone or copy this repository
2. Copy `config.example.yaml` to `config.yaml` and edit it. The example file is safe to commit; `**config.yaml` is gitignored** so you can put secrets there.
3. **Telegram:** create a bot with [@BotFather](https://t.me/BotFather), copy the bot token, and get your chat ID ([short tutorial](https://www.youtube.com/watch?v=l5YDtSLGhqk)). Put `telegram_bot_token` and `telegram_chat_id` in `config.yaml` or ENV.

*Note: the example config comments mention environment variables for secrets; the loader currently expects non-empty values in YAML unless you use `--dry-run`.*

## Configuration


| Field                             | Meaning                                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `ss_listing_url`                  | Full URL of the SS.com category/listing page to watch (must match the site’s table layout).           |
| `price_min_eur` / `price_max_eur` | Inclusive EUR bounds; rows without a parseable price are skipped.                                     |
| `deal_type`                       | `all`, `rent`, or `sale` - rent/sale is inferred from the price cell (e.g. monthly rent vs lump sum). |
| `state_db_path`                   | SQLite file for seen IDs (relative paths are resolved next to the config file).                       |
| `dry_run`                         | If true, no Telegram calls and no DB writes (see also CLI `--dry-run`).                               |
| `max_pages`                       | How many `page2.html`, `page3.html`, … pages to fetch after the first URL (1–100).                    |
| `request_timeout_sec`             | HTTP timeout for SS.com and Telegram.                                                                 |
| `delay_between_pages_sec`         | Pause between paginated requests to reduce load on the server.                                        |


## Running

From the project root (so `config.yaml` resolves correctly):

```bash
python run_ss_notifier.py
```

Or with an explicit config path:

```bash
python run_ss_notifier.py --config path/to/config.yaml
```

- `**--dry-run**` -  logs what would happen without contacting Telegram or updating the database (useful for testing filters and parsing).

Exit code is non-zero if the run fails (network, config, Telegram API, etc.).

### Avoiding a burst of alerts on first use

The first successful non–dry-run execution will notify for every **new** listing that passes filters and is not yet in the database. If the category already has many ads, you may want to **seed** the current set of matching IDs once so only *future* listings trigger alerts. The package exposes `run_seed()` in `ss_notifier.main` for that (fetch listings, apply filters, record IDs without Telegram). You can call it from a short script with `PYTHONPATH=src` or the same `sys.path` pattern as `run_ss_notifier.py`.

### Automation

Run the same command on a schedule (cron, systemd timer, Windows Task Scheduler, GitHub Actions with secrets, etc.) at an interval that respects SS.com’s terms of service and your own rate limits (`delay_between_pages_sec`, `max_pages`).

## Tests

```bash
pytest
```

`pytest.ini` sets `pythonpath = src` so imports resolve without installing the package.

## Project layout

- `run_ss_notifier.py` - entrypoint that adds `src` to `sys.path` and calls `main()`.
- `src/ss_notifier/` - config loading, HTML scraping, Telegram notifications, SQLite store.
- `sample_page.html` - fixture-style sample for understanding the expected table structure.
- `tests/` - unit tests for filters, run/seed behavior, and CLI wiring.

