"""Fail closed before smoke traffic reaches a live CMP deployment.

Only an explicit loopback target is supported until an isolated dev service
and database have been verified. There is deliberately no override flag.
"""

import os
from urllib.parse import urlsplit


class ConfigError(RuntimeError):
    """Raised when smoke configuration is missing or unsafe."""


def require_safe_base_url(base_url: str) -> str:
    message = (
        "Refusing E2E smoke target: use an explicit loopback HTTP(S) "
        "origin with a throwaway database. Production, current dev, "
        "and all other remote targets are forbidden."
    )
    try:
        parsed = urlsplit(base_url)
        safe = (
            base_url == base_url.strip()
            and not any(char.isspace() for char in base_url)
            and parsed.scheme in {"http", "https"}
            and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
        # Accessing port also rejects invalid/out-of-range ports.
        if not safe or parsed.port == 0:
            raise ConfigError(message)
    except ValueError:
        raise ConfigError(message) from None
    return base_url.rstrip("/")


def request_targets_base(url: str, base_url: str) -> bool:
    """For browser requests, including redirects and form submissions."""
    require_safe_base_url(base_url)
    try:
        target = urlsplit(url)
        base = urlsplit(base_url)
        return (
            target.scheme == base.scheme
            and target.hostname == base.hostname
            and (target.port or (443 if target.scheme == "https" else 80))
            == (base.port or (443 if base.scheme == "https" else 80))
            and target.username is None
            and target.password is None
        )
    except ValueError:
        return False


if __name__ == "__main__":
    # The workflow runs this before health checks, dependency installation,
    # credential injection, browser startup, or cleanup.
    require_safe_base_url(os.environ.get("E2E_BASE_URL", ""))
    print("E2E target safety check passed (loopback only).")
