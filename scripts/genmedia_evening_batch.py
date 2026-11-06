"""Evening genmedia batch: approve eligible pending registrations via the
CMP API (each approval queues the normal applicant decision email through
Relay), then send a plain-email CSV summary.

Runs from cron on hetzner at 20:05 Europe/Berlin daily. The first run is
manual (``--ignore-start-date``); cron takes over once START_DATE passes.

No Relay templates are used here: decisions use the standard application
emails, the summary is a plain email sent with ``datamailer send``.
"""

import csv
import io
import os
import subprocess
import sys
from datetime import date
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from courses.genmedia_policy import (  # noqa: E402
    AUTO_APPROVAL_LIMIT,
    AUTO_APPROVAL_TIMEZONE,
    CAMPAIGN_SLUG,
    excluded_reason,
)

BERLIN = ZoneInfo(AUTO_APPROVAL_TIMEZONE)
BATCH_SIZE = 100


class BatchError(RuntimeError):
    pass


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise BatchError(f"Missing required env var: {name}")
    return value


def split_recipients(raw):
    return [
        address.strip()
        for address in raw.replace(",", " ").split()
        if "@" in address
    ]


def success_recipients():
    return split_recipients(
        env(
            "GENMEDIA_SUMMARY_TO",
            default="alexey.s.grigoriev@gmail.com,mnrozhkov@nebius.com",
        )
    )


def failure_recipients():
    return split_recipients(
        env("GENMEDIA_FAILURE_TO", default="alexey.s.grigoriev@gmail.com")
    )


def api(method, path, token, base_url, payload=None, timeout=30):
    try:
        response = requests.request(
            method,
            base_url.rstrip("/") + path,
            headers={
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise BatchError(f"API {method} {path} unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise BatchError(
            f"API {method} {path} returned {response.status_code}: "
            f"{response.text[:300]}"
        )
    return response.json()


def fetch_pending(base_url, token, campaign):
    """All pending registrations for the campaign (500 per page)."""
    pending = []
    total = 0
    while True:
        body = api(
            "GET",
            f"/api/registration-campaigns/{campaign}/registrations/"
            f"?status=pending&limit=500",
            token,
            base_url,
        )
        total = body["stats"]["total"]
        rows = body["registrations"]
        pending.extend(rows)
        if len(rows) < 500:
            break
        raise BatchError("Pending overflow: more than one page")
    return pending, total


def select_approvable(pending_rows, total_count):
    """Split pending rows into (approvable, skipped) honouring policy+cap."""
    approvable = []
    skipped = []
    for row in pending_rows:
        if total_count + len(approvable) >= AUTO_APPROVAL_LIMIT:
            skipped.append((row, "cap-reached"))
            continue
        registration = SimpleNamespace(
            country=row.get("country") or "",
            ukraine_region=row.get("ukraine_region") or "",
        )
        reason = excluded_reason(registration)
        if reason:
            skipped.append((row, f"excluded-{reason}"))
        else:
            approvable.append(row)
    return approvable, skipped


def chunked(items, size):
    return [items[i : i + size] for i in range(0, len(items), size)]


def approve_batches(base_url, token, campaign, approvable, dry_run):
    approved = []
    for chunk in chunked([row["id"] for row in approvable], BATCH_SIZE):
        if dry_run:
            approved.extend(
                row for row in approvable if row["id"] in chunk
            )
            continue
        body = api(
            "POST",
            f"/api/registration-campaigns/{campaign}/registrations/"
            "approve-batch/",
            token,
            base_url,
            payload={"ids": chunk},
        )
        approved.extend(body["approved"])
        for item in body["skipped"]:
            raise BatchError(f"API skipped id={item['id']}: {item['reason']}")
    return approved


def build_csv(approved, day):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("name", "email", "country", "ukraine_region", "approved_at"))
    for row in approved:
        writer.writerow(
            (
                row.get("name") or "",
                row.get("email") or "",
                row.get("country") or "",
                row.get("ukraine_region") or "",
                day.isoformat(),
            )
        )
    return buffer.getvalue()


def send_plain_email(to, subject, body_text, idempotency_key, attachments=()):
    """Plain email via the relay CLI (no templates)."""
    url = env("DATAMAILER_URL", default="https://relay.datatalks.club")
    api_key = env("DATAMAILER_API_KEY", required=True)
    command = [
        os.path.expanduser("~/.local/bin/relay"),
        "send",
        "--url",
        url,
        "--api-key",
        api_key,
        "--to",
        to,
        "--subject",
        subject,
        "--body",
        body_text,
        "--from",
        "courses",
        "--idempotency-key",
        idempotency_key,
    ]
    for attachment in attachments:
        command.extend(["--attach", attachment])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise BatchError(f"datamailer send to {to} failed: {exc}") from exc


def notify_failure(day_label, error):
    subject = f"Genmedia batch FAILED {day_label}: {type(error).__name__}"
    body = (
        f"The evening genmedia batch failed and NOTHING was approved.\n\n"
        f"Error: {error}\n"
    )
    for recipient in failure_recipients():
        send_plain_email(
            recipient,
            subject,
            body,
            f"genmedia-evening-fail:{day_label}:{recipient}",
        )


def notify_success(day_label, approved, skipped, total, csv_path):
    with open(csv_path) as handle:
        csv_text = handle.read()
    header, _, body = csv_text.partition("\n")
    rows = body.strip().splitlines() or [""]
    subject_base = (
        f"Genmedia approved {day_label}: "
        f"{len(approved)} approved, {len(skipped)} skipped"
    )
    skipped_text = ", ".join(
        f"{row.get('email')} ({reason})" for row, reason in skipped
    ) or "none"
    chunks = chunked(rows, 60)
    total_parts = max(1, len(chunks))
    for part_no, rows_chunk in enumerate(chunks or [[]], start=1):
        part_path = "%s.p%dof%d.csv" % (csv_path, part_no, total_parts)
        with open(part_path, "w") as handle:
            handle.write(header + "\n" + "\n".join(rows_chunk) + "\n")
        lines = [
            f"Approved {len(approved)}, skipped {len(skipped)} "
            f"(campaign total now ~{total + len(approved)}).",
            "",
            "Skipped (not in the attached CSV): " + skipped_text,
            "",
            "Approved list attached as CSV part %d of %d." % (part_no, total_parts),
        ]
        for recipient in success_recipients():
            label = "" if total_parts == 1 else " [%d/%d]" % (part_no, total_parts)
            send_plain_email(
                recipient,
                subject_base + label,
                "\n".join(lines),
                "genmedia-evening:%s:%s:p%d" % (day_label, recipient, part_no),
                attachments=[part_path],
            )


def run(dry_run=False):
    day_label = __import__("datetime").datetime.now(BERLIN).date().isoformat()
    base_url = env("CMP_BASE_URL", required=True)
    token = env("CMP_API_TOKEN", required=True)
    campaign = env("CAMPAIGN_SLUG", default=CAMPAIGN_SLUG)

    pending, total = fetch_pending(base_url, token, campaign)
    approvable, skipped = select_approvable(pending, total)
    print(
        f"day={day_label} pending={len(pending)} "
        f"approvable={len(approvable)} skipped={len(skipped)} total={total}"
    )
    for row in approvable:
        print(f"  approve {row['email']} ({row.get('country')})")
    for row, reason in skipped:
        print(f"  skip {row.get('email')} ({reason})")
    if dry_run:
        print("dry-run: no approvals, no emails")
        return

    if total >= AUTO_APPROVAL_LIMIT:
        raise BatchError(
            f"Cap reached: campaign total {total} >= {AUTO_APPROVAL_LIMIT}"
        )
    approved = approve_batches(base_url, token, campaign, approvable, dry_run)
    if not approved and not skipped:
        print("nothing pending: no emails sent")
        return
    csv_path = "/tmp/opencode/genmedia-approved-%s.csv" % day_label
    with open(csv_path, "w") as handle:
        handle.write(build_csv(approved, date.fromisoformat(day_label)))
    notify_success(day_label, approved, skipped, total, csv_path)
    print(f"summary sent for {len(approved)} approved")


def main(argv):
    dry_run = "--dry-run" in argv
    ignore_start = "--ignore-start-date" in argv
    start_date = env("GENMEDIA_BATCH_START_DATE", default="2026-11-06")
    today = __import__("datetime").datetime.now(BERLIN).date().isoformat()
    if not dry_run and not ignore_start and today < start_date:
        print(f"scheduled start {start_date} not reached (today {today})")
        return 0
    try:
        run(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - must mail, then exit nonzero
        day_label = (
            __import__("datetime").datetime.now(BERLIN).date().isoformat()
        )
        try:
            if not dry_run:
                notify_failure(day_label, exc)
        except Exception as mail_exc:  # noqa: BLE001
            print(f"failure email also failed: {mail_exc}")
        print(f"FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
