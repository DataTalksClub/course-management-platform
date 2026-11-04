#!/usr/bin/env python3
"""CI/local helper: refuse e2e against anything but an explicit loopback target.

Exit 0 only when E2E_BASE_URL (or argv[1]) is a loopback HTTP(S) origin.
Mirrors ``e2e.config.assert_safe_e2e_base_url`` / ``e2e/safety.py``:
production, current dev, and all other remote targets are forbidden until
an isolated dev service and database have been verified.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_E2E = Path(__file__).resolve().parent.parent
REPO_ROOT = REPO_E2E.parent
sys.path.insert(0, str(REPO_ROOT))

from e2e.config import ConfigError, assert_safe_e2e_base_url  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        raw = argv[1]
    else:
        raw = os.environ.get("E2E_BASE_URL")
    if not raw:
        print("ERROR: E2E_BASE_URL is required (explicit loopback origin).", file=sys.stderr)
        return 1
    try:
        cleaned = assert_safe_e2e_base_url(raw.rstrip("/"))
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: e2e target {cleaned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
