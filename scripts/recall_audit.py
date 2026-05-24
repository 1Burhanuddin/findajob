#!/usr/bin/env python3
"""Weekly recall-audit cron entry point.

Samples hard-rejected and low-scored jobs from the past week, re-scores
them with a different model, and alerts if the upgrade rate exceeds 10%.
Results are written to the ``recall_audit`` table and visible at
``/stats/recall-audit``.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from findajob.metrics.recall_audit import run_audit
from findajob.paths import BASE

DB_PATH = Path(BASE) / "data" / "pipeline.db"


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        summary = run_audit(conn)
        print(f"recall-audit: {summary['upgrades']}/{summary['total']} upgrades ({summary['upgrade_rate']:.1%})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
