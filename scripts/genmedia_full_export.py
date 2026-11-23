"""Send the Genmedia participant list to Nebius: one CSV, one recipient.

This is the one entry point for the partner list (manual sends included):
run it with ``--dry-run`` first, check the printed counts, then run it
without the flag. Do not build the CSV by hand.

Source: every approved registration of the campaign, paged through the CMP
API until the server-reported count is reached (the API caps one page at
500 rows). Only rows with ``accepted_nebius_sharing`` true are exported; the
run fails if the API does not serialize that field or if the client-side
consent count disagrees with the server-side filter.

CSV: a fixed schema (``REPORT_FIELDS``), UTF-8 with BOM, one physical line
per participant, ordered by ``created_at``. It matches the 23 Nov 2026 file
approved for Mikhail, including his ``country`` and ``role`` columns.

The Hetzner cron line (Mondays 20:15 Europe/Berlin) is on HOLD since
2026-11-23; see deploy/hetzner/genmedia-crontab. The weekly run makes one
Relay CLI call, with exactly one recipient and one CSV attachment. Failures
are logged and sent to the internal ops alert hook.

Environment: CMP_BASE_URL, CMP_API_TOKEN, DATAMAILER_URL,
DATAMAILER_API_KEY, GENMEDIA_WEEKLY_REPORT_TO (defaults to the Nebius
recipient), and optionally GENMEDIA_EXPORT_DIR.
"""

import argparse
import csv
import hashlib
import io
import os
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.genmedia_alerts import report_failure  # noqa: E402
from scripts.send_big_csv import flatten  # noqa: E402
from scripts.send_campaign_export import fetch_count, fetch_status  # noqa: E402


class ExportError(RuntimeError):
    pass


REPORT_TIMEZONE = ZoneInfo("Europe/Berlin")
REPORT_START_DATE = date(2026, 11, 16)
RELAY_TIMEOUT_SECONDS = 60
REPORT_SEND_TIME = time(20, 15)
REPORT_STATUS = "approved"
CONSENT_FIELD = "accepted_nebius_sharing"
# Fixed column order agreed for Mikhail on 2026-11-23. Changing it changes
# the partner's import; update the tests and tell the recipient first.
REPORT_FIELDS = (
    "id",
    "email",
    "name",
    "company_name",
    "linkedin_url",
    "github_url",
    "status",
    "created_at",
    "auto_approved_at",
    CONSENT_FIELD,
    "country",
    "role",
)


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


def fetch_all(base_url, token, campaign):
    """Every approved registration; raises unless the API count is reached."""
    rows = fetch_status(base_url, token, campaign, REPORT_STATUS)
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ExportError("duplicate registration ids in the export")
    statuses = Counter(row.get("status") for row in rows)
    if set(statuses) - {REPORT_STATUS}:
        raise ExportError(f"unexpected statuses in the export: {dict(statuses)}")
    return rows


def shareable_rows(rows):
    """Rows whose owner agreed to share their details with Nebius."""
    if any(CONSENT_FIELD not in row for row in rows):
        raise ExportError(
            f"CMP API does not serialize {CONSENT_FIELD}; refusing to export "
            "without a consent check"
        )
    shared = [row for row in rows if row[CONSENT_FIELD] is True]
    return shared, len(rows) - len(shared)


def report_csv_text(rows):
    """Fixed-schema CSV, one physical line per participant, BOM for Excel."""
    ordered = sorted(
        rows, key=lambda row: (row.get("created_at") or "", row["id"])
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(REPORT_FIELDS)
    for row in ordered:
        writer.writerow([flatten(row.get(field)) for field in REPORT_FIELDS])
    text = buffer.getvalue()
    if len(text.splitlines()) != len(rows) + 1:
        raise ExportError("every participant row must be a single line")
    return "\ufeff" + text


def weekly_subject(shared, report_day):
    return f"Genmedia participants as of {report_day}: {shared} approved"


def weekly_body(shared, report_day):
    return (
        f"Participant list as of {report_day}: {shared} approved participants "
        "who agreed to share their details with Nebius.\n\n"
        "Attached as a single CSV file (UTF-8) with the columns "
        f"{', '.join(REPORT_FIELDS)}."
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
    shared, withheld = shareable_rows(rows)
    server_shared = fetch_count(
        base_url,
        token,
        campaign,
        {"status": REPORT_STATUS, CONSENT_FIELD: "true"},
    )
    if server_shared != len(shared):
        raise ExportError(
            f"consent count mismatch: {len(shared)} in rows, "
            f"{server_shared} from the API filter"
        )
    print(
        f"fetched {len(rows)} approved (complete); {len(shared)} shareable, "
        f"{withheld} withheld without {CONSENT_FIELD}"
    )

    export_dir = env("GENMEDIA_EXPORT_DIR", default="/tmp/opencode")
    os.makedirs(export_dir, exist_ok=True)
    csv_path = os.path.join(
        export_dir, f"genmedia-weekly-report-{report_day.isoformat()}.csv"
    )
    csv_text = report_csv_text(shared)
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(csv_text)
    digest = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    print(f"columns: {','.join(REPORT_FIELDS)}")
    print(
        f"csv rows: {len(shared)}, bytes: {os.path.getsize(csv_path)}, "
        f"sha256: {digest} -> {csv_path}"
    )

    if dry_run:
        print(
            "dry-run: 1 recipient, 1 CSV attachment prepared; no email sent"
        )
        return

    url = env("DATAMAILER_URL", default="https://relay.datatalks.club")
    api_key = env("DATAMAILER_API_KEY", required=True)
    command = build_relay_command(
        relay_bin(),
        url,
        api_key,
        recipients,
        weekly_subject(len(shared), report_day.isoformat()),
        weekly_body(len(shared), report_day.isoformat()),
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
