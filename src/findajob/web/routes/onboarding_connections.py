"""GET + POST /onboarding/connections/{session_id}/ — terminal gate (#571).

Final onboarding step: prompt for the LinkedIn ``Connections.csv`` export that
drives :mod:`findajob.find_contacts`. The user either uploads a valid CSV or
explicitly skips. Either way, the sentinel is written exactly here, replacing
gmail-config as the terminal gate that ends every onboarding flow.

Validation + atomic-write share a module with the returning-user maintenance
UI at ``/settings/connections/`` (#614) via :mod:`findajob.web.connections_upload`
— diverging validators between the two paths is a documented failure mode.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from findajob.onboarding.injector import mark_complete
from findajob.web.connections_upload import (
    MAX_BYTES,
    atomic_write_connections,
    validate_connections_csv,
)

router = APIRouter(prefix="/onboarding/connections", tags=["onboarding"])


def _ctx(session_id: str, *, validation_error: str | None = None) -> dict:
    return {
        "session_id": session_id,
        "validation_error": validation_error,
    }


@router.get("/{session_id}/", response_class=HTMLResponse)
def get_connections_gate(session_id: str, request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="onboarding_connections/index.html",
        context=_ctx(session_id),
    )


@router.post("/{session_id}/skip")
def post_skip(session_id: str, request: Request) -> Response:
    """Skip the connections upload; write sentinel; redirect to dashboard.

    Skipping is always allowed — find_contacts handles a missing file
    silently. The user can return via ``/onboarding/?mode=rerun``.
    """
    base = Path(request.app.state.base_root)
    mark_complete(base)
    return RedirectResponse("/board/dashboard", status_code=303)


@router.post("/{session_id}/upload", response_model=None)
async def post_upload(
    session_id: str,
    request: Request,
    connections_csv: UploadFile,
) -> HTMLResponse | Response:
    """Validate the uploaded CSV header, write the file atomically, write
    sentinel, redirect to dashboard.

    Strict header validation: the first row of the CSV must contain every
    column in ``REQUIRED_COLUMNS``. Anything else (LinkedIn preamble,
    column renames, partial exports) is rejected with an inline error and
    no sentinel write. The user can re-export from LinkedIn and retry, or
    fall back to Skip.
    """
    templates = request.app.state.templates
    base = Path(request.app.state.base_root)

    raw = await connections_csv.read(MAX_BYTES + 1)
    error, _ = validate_connections_csv(raw)
    if error is not None:
        return templates.TemplateResponse(
            request=request,
            name="onboarding_connections/index.html",
            context=_ctx(session_id, validation_error=error),
            status_code=400,
        )

    atomic_write_connections(base, raw)
    mark_complete(base)
    return RedirectResponse("/board/dashboard", status_code=303)
