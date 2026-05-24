#!/usr/bin/env python3
"""Daily drift-alerting cron entry point.

Scans ``config_changes`` for rows exactly 7 days old, computes before/after
key metrics (precision, cost-per-applied), and fires an ntfy alert when the
delta exceeds threshold (>15% precision shift, >25% cost shift).
"""

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from findajob.db import connect
from findajob.metrics.stats import before_after_metrics
from findajob.notifications.ntfy import send
from findajob.paths import BASE

DB_PATH = Path(BASE) / "data" / "pipeline.db"

PRECISION_THRESHOLD_PP = 15.0
COST_THRESHOLD_PCT = 25.0
LOOKBACK_DAY = 7


def main() -> None:
    conn = connect(DB_PATH)

    target_date = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAY)).strftime("%Y-%m-%d")

    changes = conn.execute(
        """
        SELECT DISTINCT lever, date(changed_at) AS day
        FROM config_changes
        WHERE date(changed_at) = ?
        """,
        (target_date,),
    ).fetchall()

    if not changes:
        print(f"drift-alert: no config changes on {target_date}")
        conn.close()
        return

    for row in changes:
        lever = row["lever"] if isinstance(row, sqlite3.Row) else row[0]
        day = row["day"] if isinstance(row, sqlite3.Row) else row[1]

        metrics = before_after_metrics(conn, day)
        delta = metrics.get("delta", {})
        before = metrics.get("before", {})
        after = metrics.get("after", {})

        alerts = []
        precision_delta = delta.get("precision_pct")
        cost_delta = delta.get("cost_pct")

        if precision_delta is not None and abs(precision_delta) > PRECISION_THRESHOLD_PP:
            direction = "up" if precision_delta > 0 else "down"
            alerts.append(
                f"reject rate {before['precision_pct']}%→{after['precision_pct']}% "
                f"({direction} {abs(precision_delta):.1f}pp)"
            )

        if cost_delta is not None and abs(cost_delta) > COST_THRESHOLD_PCT:
            direction = "up" if cost_delta > 0 else "down"
            alerts.append(
                f"cost/applied ${before['cost_per_applied']}→${after['cost_per_applied']} "
                f"({direction} {abs(cost_delta):.1f}%)"
            )

        if alerts:
            body = f"7 days after editing {lever}: {'; '.join(alerts)}. Review at /stats/funnel"
            send(
                title=f"Drift alert: {lever}",
                body=body,
                priority="default",
                tags="chart_with_upwards_trend",
                kind="drift_alert",
                cta_url="/stats/funnel",
            )
            print(f"drift-alert: FIRED for {lever} on {day}: {'; '.join(alerts)}")
        else:
            print(f"drift-alert: {lever} on {day} — no significant shift")

    conn.close()


if __name__ == "__main__":
    main()
