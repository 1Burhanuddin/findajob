#!/usr/bin/env python3
"""Print a single value from a ``data/.env``-style file (#684).

Use instead of ``bash -c 'set -a; . data/.env; set +a; printf %s "$KEY"'``,
which silently fails on values containing shell metacharacters (paths,
spaces, unquoted special chars) because bash evaluates the RHS as a shell
expression. This helper delegates to ``findajob.paths.load_env``, which
reads values literally and strips outer quotes uniformly.

    $ scripts/read_env_value.py --key NTFY_TOPIC
    my-ntfy-topic

    $ scripts/read_env_value.py --path /srv/example/state/data/.env --key OPENROUTER_API_KEY

Exits 1 if the file is missing or the key is not present.
"""

from __future__ import annotations

import argparse
import os
import sys

from findajob.paths import BASE, load_env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", required=True, help="Variable name to read")
    parser.add_argument(
        "--path",
        default=f"{BASE}/data/.env",
        help="Path to .env file (default: data/.env under BASE)",
    )
    args = parser.parse_args()

    path = os.path.expanduser(args.path)
    if not os.path.isfile(path):
        print(f"read_env_value: file not found: {path}", file=sys.stderr)
        return 1

    env = load_env(path)
    if args.key not in env:
        print(f"read_env_value: key not found: {args.key}", file=sys.stderr)
        return 1

    print(env[args.key])
    return 0


if __name__ == "__main__":
    sys.exit(main())
