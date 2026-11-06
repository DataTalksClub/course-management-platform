"""Daily full genmedia participant export emailed via the relay CLI.

Runs from cron on hetzner after the evening approval batch (suggested:
20:15 Europe/Berlin daily). Fetches every registration of the campaign
(all statuses, all participant fields) and sends ONE `relay send` call
with a repeatable --to per recipient and the full CSV as a single
--attach file. Gmail threads the per-recipient sends by subject.

Prerequisites:
  * relay CLI with repeatable --to (post cli-multi-recipient release).
  * WAF exception for the hetzner egress IP (aws-infra#106 applied):
    without it the edge blocks the >8KiB request with 403.
  * Env: CMP_BASE_URL, CMP_API_TOKEN (same as the evening batch),
    DATAMAILER_URL, DATAMAILER_API_TOKEN, GENMEDIA_FULL_EXPORT_TO
    (default "alexey.s.grigoriev@gmail.com,mnrozhkov@nebius.com").

Crontab example (hetzner, Europe/Berlin) — mirrors the evening batch line:
  15 20 * * * set -a; . /home/alexey/.config/genmedia-batch.env; set +a; /usr/bin/flock -n /home/alexey/.local/state/genmedia-full-export.lock /home/alexey/git/course-management-platform/.venv/bin/python /home/alexey/git/course-management-platform/scripts/genmedia_full_export.py >> /home/alexey/.local/state/genmedia-full-export.log 2>&1
"""

import os
import subprocess
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.send_big_csv import rows_to_csv_text  # noqa: E402
from scripts.send_campaign_export import (  # noqa: E402
    build_body,
    build_subject,
    fetch_all,
)


class ExportError(RuntimeError):
    pass


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ExportError(f"Missing required env var: {name}")
    return value


def split_recipients(raw):
    return [
        address.strip()
        for address in raw.replace(",", " ").split()
        if "@" in address
    ]


def export_recipients():
    return split_recipients(
        env(
            "GENMEDIA_FULL_EXPORT_TO",
            default="alexey.s.grigoriev@gmail.com,mnrozhkov@nebius.com",
        )
    )


def relay_bin():
    return env("RELAY_BIN", default=os.path.expanduser("~/.local/bin/relay"))


def build_relay_command(binary, url, api_key, recipients, subject, body_text,
                        idempotency_key, attachments):
    """Single `relay send` with repeatable --to and --attach (pure)."""
    command = [
        binary, "send",
        "--url", url,
        "--api-key", api_key,
    ]
    for recipient in recipients:
        command.extend(["--to", recipient])
    command.extend([
        "--subject", subject,
        "--body", body_text,
        "--from", "courses",
        "--idempotency-key", idempotency_key,
    ])
    for attachment in attachments:
        command.extend(["--attach", attachment])
    return command


def run():
    from courses.genmedia_policy import CAMPAIGN_SLUG  # noqa: E402

    day = date.today().isoformat()
    base_url = env("CMP_BASE_URL", required=True)
    token = env("CMP_API_TOKEN", required=True)
    campaign = env("CAMPAIGN_SLUG", default=CAMPAIGN_SLUG)
    recipients = export_recipients()
    if not recipients:
        raise ExportError("No recipients in GENMEDIA_FULL_EXPORT_TO")

    rows = fetch_all(base_url, token, campaign)
    counts = Counter(row["status"] for row in rows)
    total = len(rows)
    print(f"fetched {total} ({counts['approved']} approved, "
          f"{counts['pending']} pending, {counts['rejected']} rejected)")

    csv_path = f"/tmp/opencode/genmedia-full-export-{day}.csv"
    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write(rows_to_csv_text(rows))
    print(f"csv bytes: {os.path.getsize(csv_path)} -> {csv_path}")

    url = env("DATAMAILER_URL", default="https://relay.datatalks.club")
    api_key = env("DATAMAILER_API_KEY", required=True)
    command = build_relay_command(
        relay_bin(), url, api_key, recipients,
        build_subject(total), build_body(total, counts, day),
        f"genmedia-full-export:{day}", [csv_path],
    )
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ExportError(f"relay send failed: {exc}") from exc
    print(completed.stdout.strip())
    print(f"sent full export ({total} rows) to {recipients}")


def main():
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - cron must log, then exit nonzero
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
