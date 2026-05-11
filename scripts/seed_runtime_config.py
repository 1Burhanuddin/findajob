#!/usr/bin/env python3
"""Entry-point shim for fresh-install runtime-config seeding (#627).

Invoked from ``ops/entrypoint.sh`` at every container start, after the
bundled-config copy. No-op when every seeded config already exists.

Usage:
    python3 scripts/seed_runtime_config.py [BASE]

If no BASE is given, defaults to ``findajob.paths.BASE``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from findajob.config_seed import seed_runtime_config
from findajob.paths import BASE

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(BASE)
created = seed_runtime_config(base)
for path in created:
    print(f"seeded {path} from .example")
