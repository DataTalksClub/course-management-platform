"""Export all registrations of a CMP registration campaign and email the
full CSV with all participant fields via direct SES SMTP.

Same channel as scripts/send_big_csv.py (one email, single attachment,
bypasses Relay's ~8KB edge body cap). Nothing goes through Relay, so these
mails do not appear in Relay's send history/audit.

Recipients must be passed explicitly with --to (no defaults).

Example:
  python scripts/send_campaign_export.py \\
      --campaign production-ai-agents-generative-media \\
      --to me@example.com --to peer@example.com --dry-run
"""

import argparse
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from scripts.send_big_csv import (  # noqa: E402
    build_message,
    load_credentials,
    rows_to_csv_text,
    send_message,
)


def cmp_env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def fetch_status(base_url, token, campaign, status):
    """All registrations of one status (500 per page; per-status counts fit)."""
    response = requests.get(
        f"{base_url.rstrip('/')}/api/registration-campaigns/{campaign}/"
        f"registrations/?status={status}&limit=500",
        headers={"Authorization": f"Token {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["registrations"]


def fetch_all(base_url, token, campaign):
    rows = []
    for status in ("approved", "pending", "rejected"):
        rows.extend(fetch_status(base_url, token, campaign, status))
    ids = [row["id"] for row in rows]
    assert len(set(ids)) == len(ids), "duplicate registration ids"
    rows.sort(key=lambda row: row.get("created_at") or "")
    return rows


def build_subject(total):
    return f"Genmedia registrations so far: {total} (full CSV attached)"


def build_body(total, counts, day):
    return (
        f"Full export as of {day}: {total} registrations "
        f"({counts['approved']} approved, {counts['pending']} pending, "
        f"{counts['rejected']} rejected).\n\n"
        "Complete list attached as a single CSV file with all participant "
        "fields: id, email, name, company_name, campaign, course, country, "
        "region, ukraine_region, role, role_display, comment, status, "
        "created_at.\n"
        "Note: line breaks inside comment fields were flattened to spaces."
    )


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign",
                        default="production-ai-agents-generative-media")
    parser.add_argument("--to", dest="recipients", action="append", required=True,
                        help="Recipient email (repeatable). No defaults.")
    parser.add_argument("--credentials", default=os.environ.get(
        "SES_SMTP_CREDENTIALS",
        "/home/alexey/tmp/secrets/shared-ses-smtp-credentials.json"))
    parser.add_argument("--csv-out", default=None,
                        help="Keep a copy of the CSV at this path.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and build everything; send nothing.")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    base_url = cmp_env("CMP_BASE_URL", default="https://courses.datatalks.club")
    token = cmp_env("CMP_API_TOKEN", required=True)

    rows = fetch_all(base_url, token, args.campaign)
    counts = Counter(row["status"] for row in rows)
    total = len(rows)
    print(f"fetched {total} ({counts['approved']} approved, "
          f"{counts['pending']} pending, {counts['rejected']} rejected)")

    csv_text = rows_to_csv_text(rows)
    day = date.today().isoformat()
    csv_path = args.csv_out or (
        f"/tmp/opencode/{args.campaign}-full-{day}.csv")
    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write(csv_text)
    print(f"csv bytes: {os.path.getsize(csv_path)} -> {csv_path}")

    credentials = load_credentials(args.credentials)
    message = build_message(
        credentials["from_email"], args.recipients,
        build_subject(total), build_body(total, counts, day), [csv_path],
    )
    print(f"mime bytes: {len(message.as_bytes())} to={args.recipients}")
    if args.dry_run:
        print("dry-run: nothing sent")
        return 0
    send_message(credentials, message, args.recipients)
    print(f"SENT via direct SES SMTP to {args.recipients}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
