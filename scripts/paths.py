"""
Central path and base-directory resolver for all pipeline scripts.

BASE is derived from this file's location — works wherever the repo is cloned,
regardless of directory name or home folder. No hardcoded paths.

Binary paths (AICHAT, PANDOC, RCLONE) are read from config/paths.env.
Defaults are Linux-appropriate; macOS users set overrides in that file.

Usage in scripts/*.py:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paths import BASE, AICHAT, PANDOC, RCLONE

Usage in scripts/diag/*.py:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    from paths import BASE, AICHAT, PANDOC, RCLONE

Use sys.executable (not a PYTHON constant) for subprocess calls to other pipeline scripts.
"""
import os
import pathlib

# Repo root = parent of the directory containing this file (scripts/paths.py → repo root)
BASE: str = str(pathlib.Path(__file__).parent.parent.resolve())

# Allow env-var override for non-standard install locations or testing
if 'JSP_BASE' in os.environ:
    BASE = str(pathlib.Path(os.environ['JSP_BASE']).resolve())

# Load binary paths from config/paths.env
_cfg: dict = {}
_penv = pathlib.Path(BASE) / 'config' / 'paths.env'
if _penv.exists():
    for _line in _penv.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _, _v = _line.partition('=')
            _cfg[_k.strip()] = os.path.expanduser(_v.strip().strip('"').strip("'"))

# Binary paths — defaults are Linux-appropriate.
# macOS and other users: set these in config/paths.env (see config/paths.env.example).
AICHAT: str = _cfg.get('AICHAT_NG', '/usr/local/bin/aichat-ng')
PANDOC: str  = _cfg.get('PANDOC',    '/usr/bin/pandoc')
RCLONE: str  = _cfg.get('RCLONE',    '/usr/bin/rclone')
