"""Collect static files with a throwaway key during image builds."""

import os
from pathlib import Path
import secrets
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["SECRET_KEY"] = secrets.token_urlsafe(64)
    subprocess.run(
        [
            sys.executable,
            str(root / "manage.py"),
            "collectstatic",
            "--noinput",
            *sys.argv[1:],
        ],
        cwd=root,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
