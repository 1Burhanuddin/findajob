#!/usr/bin/env python3
"""One-shot migration: rename slug-based company names for Ashby/Lever jobs.

The Ashby/Lever fetchers previously stored the URL slug as the company
name (e.g., "zoox", "cobot", "helion", "sanctuary", "serverobotics").
#46 changed the fetchers to emit display names; this script fixes up
existing rows so old and new jobs from the same company unify.

Reads the display-name mapping from feed_urls.txt via the same parser
the fetchers use, so the mapping stays in one place.

Idempotent — safe to re-run.

Usage:  python3 scripts/migrate_ashby_lever_company_names.py
"""

import re
import sqlite3
import sys
from pathlib import Path

from findajob.cleaning import clean_company
from findajob.fetchers import _parse_feed_slugs
from findajob.paths import BASE

DB_PATH = Path(BASE) / "data" / "pipeline.db"
FEEDS = Path(BASE) / "config" / "feed_urls.txt"


def migrate() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    if not FEEDS.exists():
        print(f"ERROR: feed_urls.txt not found at {FEEDS}", file=sys.stderr)
        sys.exit(1)

    ashby_map = dict(_parse_feed_slugs(str(FEEDS), re.compile(r"ashbyhq\.com/([A-Za-z0-9_.-]+)")))
    lever_map = dict(_parse_feed_slugs(str(FEEDS), re.compile(r"lever\.co/([A-Za-z0-9_.-]+)")))

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    updates = 0
    for source_label, mapping in (("ashby_json", ashby_map), ("lever_json", lever_map)):
        for slug, display in mapping.items():
            normalized = clean_company(display)
            if not normalized or normalized == slug:
                continue
            # Match by either the raw slug or its clean_company form — the
            # old fetcher called clean_company(slug), which may have
            # transformed it further.
            cur = conn.execute(
                "UPDATE jobs SET company=? WHERE source=? AND company IN (?, ?)",
                (normalized, source_label, slug, clean_company(slug)),
            )
            if cur.rowcount:
                print(f"  {source_label:<12}  {slug!r} → {normalized!r}  ({cur.rowcount} rows)")
                updates += cur.rowcount

    conn.commit()
    conn.close()
    print(f"\nMigration complete — {updates} rows updated.")


if __name__ == "__main__":
    migrate()
