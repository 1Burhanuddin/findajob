"""Tests for ``scripts/read_env_value.py`` (#684).

The script is a Python-side CLI for reading a single value from a
``data/.env`` file. It exists because bash-sourcing (``set -a; . data/.env;
set +a``) silently errors on unquoted values containing shell metacharacters
— a path like ``/srv/example/foo`` is treated as a command and fails with
``Permission denied`` while still appearing to "load" the file. Python-side
parsing reads values literally, sidestepping the failure mode.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(env_path: Path, key: str) -> subprocess.CompletedProcess[str]:
    """Invoke the helper script with ``--path`` and ``--key``."""
    script = Path(__file__).parent.parent / "scripts" / "read_env_value.py"
    return subprocess.run(
        [sys.executable, str(script), "--path", str(env_path), "--key", key],
        capture_output=True,
        text=True,
    )


def test_unquoted_value_with_slashes(tmp_path: Path) -> None:
    """Unquoted path-with-slashes — the exact failure mode bash sourcing hits."""
    env = tmp_path / ".env"
    env.write_text("WORKDIR=/srv/example/state\n")
    result = _run(env, "WORKDIR")
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == "/srv/example/state"


def test_double_quoted_value_with_space(tmp_path: Path) -> None:
    """Double-quoted value with embedded space — outer quotes stripped."""
    env = tmp_path / ".env"
    env.write_text('LABEL="my stack name"\n')
    result = _run(env, "LABEL")
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == "my stack name"


def test_single_quoted_value(tmp_path: Path) -> None:
    """Single-quoted value — outer quotes stripped, same as double."""
    env = tmp_path / ".env"
    env.write_text("TOPIC='my-ntfy-topic'\n")
    result = _run(env, "TOPIC")
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == "my-ntfy-topic"


def test_key_not_present(tmp_path: Path) -> None:
    """Missing key exits non-zero with diagnostic on stderr."""
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n")
    result = _run(env, "BAZ")
    assert result.returncode == 1
    assert "BAZ" in result.stderr


def test_file_missing(tmp_path: Path) -> None:
    """Missing file exits non-zero rather than silently emitting empty."""
    env = tmp_path / "nope.env"
    result = _run(env, "WHATEVER")
    assert result.returncode == 1
    assert "nope.env" in result.stderr


def test_comments_and_blank_lines_skipped(tmp_path: Path) -> None:
    """Mirror ``findajob.paths.load_env`` semantics for comments + blanks."""
    env = tmp_path / ".env"
    env.write_text("# leading comment\n\nFIRST=one\n# inline-style: this whole line is a comment\nSECOND=two\n")
    result = _run(env, "SECOND")
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == "two"
