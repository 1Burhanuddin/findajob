"""Idempotent fresh-install seeding for runtime config files (#627).

Runs once per container start (``ops/entrypoint.sh``), right after the
bundled-config copy plants ``.example`` variants in ``$BASE/config/``.
Materializes the small number of gitignored config files that have a
hard 500-on-missing code path. Other ``.example`` configs (e.g.
``active_sources.txt``, ``in_domain_patterns.yaml``) have safe-default
or operator-supplied handling in their reader code and intentionally
stay absent until the operator/onboarding produces them.

Mirrors the ``init_db.py`` pattern: a tiny Python module owns the state
change, the shell entrypoint just dispatches.
"""

from __future__ import annotations

from pathlib import Path

# .example → live filename pairs. Only entries whose absence causes an
# unhandled 500 belong here.
_SEED_PAIRS: tuple[tuple[str, str], ...] = (("config/rapidapi_feeds.yaml.example", "config/rapidapi_feeds.yaml"),)


def seed_runtime_config(base: Path) -> list[Path]:
    """Materialize listed ``.example → live`` configs that don't already exist.

    Returns the live paths that were newly created (empty list on a no-op
    run). Existing live files are never overwritten — operator edits
    survive container restarts.
    """
    created: list[Path] = []
    for example_rel, target_rel in _SEED_PAIRS:
        target = base / target_rel
        if target.exists():
            continue
        example = base / example_rel
        if not example.exists():
            continue
        target.write_text(example.read_text())
        created.append(target)
    return created
