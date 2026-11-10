"""Evening genmedia batch: approve eligible pending registrations via the
CMP API. The daily job sends no sponsor report; weekly statistics are sent by
``genmedia_full_export.py``.

Runs from cron on hetzner at 20:05 Europe/Berlin daily. The first run is
manual (``--ignore-start-date``); cron takes over once START_DATE passes.

The approval API owns applicant notifications. This script never sends an
email to Nebius.
"""

import csv
import io
import os
import sys
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
from scripts.genmedia_alerts import report_failure  # noqa: E402

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


def notify_failure(day_label, error):
    report_failure(f"Genmedia daily approval batch {day_label}", error)


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
        print("nothing pending: no Nebius report sent")
        return
    print(
        f"daily approval complete: {len(approved)} approved, "
        f"{len(skipped)} skipped; no Nebius report sent"
    )


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
    except Exception as exc:  # noqa: BLE001 - must alert, then exit nonzero
        day_label = (
            __import__("datetime").datetime.now(BERLIN).date().isoformat()
        )
        try:
            if not dry_run:
                notify_failure(day_label, exc)
        except Exception as alert_exc:  # noqa: BLE001
            print(f"failure alert also failed: {alert_exc}", file=sys.stderr)
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
