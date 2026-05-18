"""Shared validation + atomic write for LinkedIn ``connections.csv`` uploads.

Used by both the onboarding gate (`/onboarding/connections/`, #571) and the
returning-user settings page (`/settings/connections/`, #614). Factoring this
once prevents validator drift — diverging accept/reject behavior between the
two upload paths would surface as "my refresh succeeded but onboarding rejects
the same file."
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from pathlib import Path

# Mirrors the columns read by findajob.find_contacts. First Name / Last Name
# are hard-required (KeyError without them); the rest are .get()'d but
# contribute no signal if absent. Validating all six up front gives a clear
# error before the user discovers prep produces zero outreach drafts.
REQUIRED_COLUMNS = ("First Name", "Last Name", "Company", "Position", "Connected On", "URL")

# Bound the multipart read so an oversize or wrong-content upload can't OOM
# the worker. A LinkedIn connections export of 30,000 connections fits well
# inside 16 MiB.
MAX_BYTES = 16 * 1024 * 1024


def validate_connections_csv(raw: bytes) -> tuple[str | None, str]:
    """Validate header + size + encoding of an uploaded connections.csv.

    Returns ``(error_message, decoded_text)``. On success the error is None
    and the decoded text (UTF-8-sig, BOM stripped) is returned so the caller
    can avoid re-decoding for any downstream work. On failure the error is
    a human-readable string and the decoded text is empty.

    The caller is responsible for the size pre-check before reading — pass
    a slice of up to ``MAX_BYTES + 1`` bytes; if it exceeds ``MAX_BYTES``
    the function reports the size error.
    """
    if len(raw) > MAX_BYTES:
        return (
            f"Upload exceeds the {MAX_BYTES // (1024 * 1024)} MiB ceiling. "
            "Re-export with the Connections-only option (smaller).",
            "",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return (
            "We couldn't read the file as UTF-8 text. Make sure you uploaded "
            "the Connections.csv from inside the LinkedIn data-export ZIP, "
            "not the ZIP itself.",
            "",
        )

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return ("The file is empty. Re-export from LinkedIn and try again.", "")

    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        return (
            f"The first row of the CSV is missing required columns: {', '.join(missing)}. "
            "Expected the LinkedIn Connections export header — "
            "First Name, Last Name, Company, Position, Connected On, URL. "
            "If your file has a 'Notes:' preamble at the top, delete those lines "
            "(plus the blank line that follows) so the column headers are on row 1.",
            "",
        )

    return (None, text)


def connections_path(base: Path) -> Path:
    """Canonical destination for an uploaded connections.csv on this stack."""
    return base / "data" / "connections.csv"


def atomic_write_connections(base: Path, raw: bytes) -> Path:
    """Write ``raw`` to ``data/connections.csv`` atomically.

    Payload lands in a tempfile in the same directory as the destination,
    then ``os.replace`` swaps it in. Prevents partial-file visibility to a
    prep run that races the upload. Returns the destination path.
    """
    dest = connections_path(base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".connections_upload_", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        os.replace(tmp_path, dest)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return dest


def count_connections_rows(path: Path) -> int:
    """Count data rows (excluding header) in a connections.csv.

    Returns 0 if the file is missing or unreadable. Uses ``csv.reader`` so
    embedded commas/newlines in quoted fields don't inflate the count.
    """
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            try:
                next(reader)
            except StopIteration:
                return 0
            return sum(1 for _ in reader)
    except OSError:
        return 0
