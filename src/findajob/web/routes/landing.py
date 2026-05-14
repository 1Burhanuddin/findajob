"""Landing page at /."""

from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from findajob.web.routes.materials import get_db

router = APIRouter()


_STAGES_ORDER = [
    "scored",
    "manual_review",
    "prep_in_progress",
    "materials_drafted",
    "applied",
    "interview",
    "offer",
    "waitlisted",
    "rejected",
    "not_selected",
]


@router.get("/", response_class=HTMLResponse)
def landing(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),  # noqa: B008
) -> HTMLResponse:
    from findajob.cost_rollups import projected_monthly, weekly_spend

    rows = db.execute("SELECT stage, COUNT(*) AS n FROM jobs GROUP BY stage").fetchall()
    counts = {r["stage"]: r["n"] for r in rows}
    ordered = [(s, counts.get(s, 0)) for s in _STAGES_ORDER]

    try:
        tz = os.environ.get("TZ", "UTC")
        weeks = weekly_spend(db, weeks=4, tz=tz)
        projected = projected_monthly(db)
        this_week = weeks[-1] if weeks else None
        cost_widget = {
            "tz": tz,
            "weekly_prep": this_week.prep_usd if this_week else None,
            "weekly_scoring": this_week.scoring_usd if this_week else None,
            "projected_prep": projected.prep_usd,
            "projected_scoring": projected.scoring_usd,
        }
    except sqlite3.OperationalError:
        cost_widget = None

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"ordered": ordered, "cost_widget": cost_widget},
    )
