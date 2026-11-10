"""Send the weekly Genmedia statistics and one CSV attachment via Relay.

The Hetzner cron runs on Mondays at 20:15 Europe/Berlin. Its first scheduled
send is Monday 16 November 2026. The daily approval job does not send this
report.

The weekly run makes one Relay CLI call, with exactly one recipient and one
CSV attachment. Failures are logged and sent to the internal ops alert hook.

Environment: CMP_BASE_URL, CMP_API_TOKEN, DATAMAILER_URL,
DATAMAILER_API_KEY, GENMEDIA_WEEKLY_REPORT_TO (defaults to the Nebius
recipient), and optionally GENMEDIA_EXPORT_DIR.
"""

import argparse
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.genmedia_alerts import report_failure  # noqa: E402
from scripts.send_big_csv import rows_to_csv_text  # noqa: E402
from scripts.send_campaign_export import fetch_all  # noqa: E402


class ExportError(RuntimeError):
    pass


REPORT_TIMEZONE = ZoneInfo("Europe/Berlin")
REPORT_START_DATE = date(2026, 11, 16)
RELAY_TIMEOUT_SECONDS = 60
REPORT_SEND_TIME = time(20, 15)


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


def weekly_report_recipients():
    recipients = split_recipients(
        env("GENMEDIA_WEEKLY_REPORT_TO", default="mnrozhkov@nebius.com")
    )
    if len(recipients) != 1:
        raise ExportError(
            "GENMEDIA_WEEKLY_REPORT_TO must contain exactly one recipient"
        )
    return recipients


def relay_bin():
    return env("RELAY_BIN", default=os.path.expanduser("~/.local/bin/relay"))


def build_relay_command(binary, url, api_key, recipients, subject, body_text,
                        idempotency_key, attachments):
    """Build one Relay send command with its recipient and CSV attachment."""
    if len(recipients) != 1:
        raise ExportError("weekly report requires exactly one recipient")
    if len(attachments) != 1:
        raise ExportError("weekly report requires exactly one attachment")
    command = [
        binary,
        "send",
        "--url",
        url,
        "--api-key",
        api_key,
    ]
    for recipient in recipients:
        command.extend(["--to", recipient])
    command.extend(
        [
            "--subject",
            subject,
            "--body",
            body_text,
            "--from",
            "courses",
            "--idempotency-key",
            idempotency_key,
        ]
    )
    for attachment in attachments:
        command.extend(["--attach", attachment])
    return command


def weekly_subject(total, report_day):
    return f"Genmedia weekly stats as of {report_day}: {total} registrations"


def weekly_body(total, counts, report_day):
    return (
        f"Weekly statistics as of {report_day}: {total} registrations "
        f"({counts['approved']} approved, {counts['pending']} pending, "
        f"{counts['rejected']} rejected).\n\n"
        "The current registration list is attached as a single CSV file with "
        "all participant fields. Line breaks inside comments are flattened "
        "to spaces."
    )


def run(dry_run=False, now=None):
    now = now or datetime.now(REPORT_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=REPORT_TIMEZONE)
    local_now = now.astimezone(REPORT_TIMEZONE)
    report_day = local_now.date()
    if not dry_run:
        if report_day < REPORT_START_DATE:
            raise ExportError(
                f"weekly report starts on {REPORT_START_DATE.isoformat()}"
            )
        if report_day.weekday() != 0:
            raise ExportError("weekly report can only be sent on Monday")
        if local_now.time().replace(tzinfo=None) < REPORT_SEND_TIME:
            raise ExportError("weekly report cannot be sent before 20:15 Europe/Berlin")

    from courses.genmedia_policy import CAMPAIGN_SLUG  # noqa: E402

    base_url = env("CMP_BASE_URL", required=True)
    token = env("CMP_API_TOKEN", required=True)
    campaign = env("CAMPAIGN_SLUG", default=CAMPAIGN_SLUG)
    recipients = weekly_report_recipients()

    rows = fetch_all(base_url, token, campaign)
    counts = Counter(row["status"] for row in rows)
    total = len(rows)
    print(
        f"fetched {total} ({counts['approved']} approved, "
        f"{counts['pending']} pending, {counts['rejected']} rejected)"
    )

    export_dir = env("GENMEDIA_EXPORT_DIR", default="/tmp/opencode")
    os.makedirs(export_dir, exist_ok=True)
    csv_path = os.path.join(
        export_dir, f"genmedia-weekly-report-{report_day.isoformat()}.csv"
    )
    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write(rows_to_csv_text(rows))
    print(f"csv bytes: {os.path.getsize(csv_path)} -> {csv_path}")

    if dry_run:
        print("dry-run: one recipient and one CSV prepared; no email sent")
        return

    url = env("DATAMAILER_URL", default="https://relay.datatalks.club")
    api_key = env("DATAMAILER_API_KEY", required=True)
    command = build_relay_command(
        relay_bin(),
        url,
        api_key,
        recipients,
        weekly_subject(total, report_day.isoformat()),
        weekly_body(total, counts, report_day.isoformat()),
        f"genmedia-weekly-report:{report_day.isoformat()}",
        [csv_path],
    )
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=RELAY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ExportError(
            f"Relay send timed out after {RELAY_TIMEOUT_SECONDS} seconds"
        ) from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[:500]
        suffix = f": {detail}" if detail else " (no Relay error output)"
        raise ExportError(
            f"Relay send exited with status {exc.returncode}{suffix}"
        ) from None
    except OSError as exc:
        raise ExportError(f"could not start Relay CLI: {exc}") from None

    print(completed.stdout.strip())
    print(f"sent one weekly report with one CSV to {recipients[0]}")


def main(argv=None, now=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and build the report without sending an email.",
    )
    args = parser.parse_args(argv)
    try:
        run(dry_run=args.dry_run, now=now)
    except Exception as exc:  # noqa: BLE001 - cron must log and alert on errors
        report_failure("Genmedia weekly report", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
