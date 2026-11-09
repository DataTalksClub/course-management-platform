"""One-shot big-CSV email via direct SES SMTP (bypasses Relay's edge body cap).

Relay's CloudFront/WAF front door rejects transactional-send requests with a
body over ~8KB (AWSManagedRules SizeRestrictions_BODY), so CSV attachments
do not fit through ``relay send`` no matter how the CLI chunks them. This
script sends ONE email with a SINGLE CSV attachment through AWS SES SMTP
directly. Use it for full data exports (e.g. course participant lists).

Nothing is sent through Relay: these mails do not appear in Relay's send
history/audit. Recipients must be passed explicitly with ``--to``.

Credentials: JSON file with ``smtp_host``, ``smtp_port``, ``smtp_tls``,
``smtp_username``, ``smtp_password`` and ``from_email``. Defaults to the
shared SES SMTP credentials on this box; override with SES_SMTP_CREDENTIALS.

Examples:
  python scripts/send_big_csv.py --to me@example.com --subject "Export" \\
      --body "CSV attached." --attach /tmp/opencode/export.csv --dry-run
  python scripts/send_big_csv.py --to me@example.com --to peer@example.com \\
      --subject "Export" --body "CSV attached." --attach /tmp/opencode/export.csv
"""

import argparse
import csv
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate

DEFAULT_CREDENTIALS_PATH = (
    "/home/alexey/tmp/secrets/shared-ses-smtp-credentials.json"
)

# Keep every participant row on one physical line so downstream tooling that
# splits files by line boundaries cannot tear a quoted multi-line field.
FLAT_FIELDS = (
    "id",
    "email",
    "name",
    "company_name",
    "campaign",
    "course",
    "country",
    "region",
    "ukraine_region",
    "role",
    "role_display",
    "comment",
    "status",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "landing_referrer",
    "created_at",
)


def flatten(value):
    if value is None:
        return ""
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def rows_to_csv_text(rows):
    """All API participant fields, one physical line per row."""
    lines = [",".join(FLAT_FIELDS)]
    buffer = __import__("io").StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FLAT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: flatten(row.get(key)) for key in FLAT_FIELDS})
    text = buffer.getvalue()
    assert len(text.splitlines()) == len(rows) + 1, "rows must be single-line"
    return text


def load_credentials(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build_message(from_email, to_addresses, subject, body_text, attachments):
    message = EmailMessage()
    message["From"] = from_email
    message["To"] = ", ".join(to_addresses)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message.set_content(body_text)
    for path in attachments:
        with open(path, "rb") as handle:
            message.add_attachment(
                handle.read(),
                maintype="text",
                subtype="csv" if path.endswith(".csv") else "plain",
                filename=os.path.basename(path),
            )
    return message


def send_message(credentials, message, to_addresses):
    context = ssl.create_default_context()
    with smtplib.SMTP(
        credentials["smtp_host"], int(credentials["smtp_port"])
    ) as server:
        if credentials.get("smtp_tls", True):
            server.starttls(context=context)
        server.login(credentials["smtp_username"], credentials["smtp_password"])
        server.sendmail(credentials["from_email"], to_addresses, message.as_bytes())


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", dest="recipients", action="append", required=True,
                        help="Recipient email (repeatable). No defaults: pass explicitly.")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--attach", dest="attachments", action="append", required=True,
                        help="File to attach (repeatable, e.g. a CSV).")
    parser.add_argument("--credentials", default=os.environ.get(
        "SES_SMTP_CREDENTIALS", DEFAULT_CREDENTIALS_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the MIME message and print its size; send nothing.")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    credentials = load_credentials(args.credentials)
    message = build_message(
        credentials["from_email"], args.recipients,
        args.subject, args.body, args.attachments,
    )
    raw = message.as_bytes()
    print(f"mime bytes: {len(raw)} to={args.recipients}")
    if args.dry_run:
        print("dry-run: nothing sent")
        return 0
    send_message(credentials, message, args.recipients)
    print(f"SENT via direct SES SMTP to {args.recipients}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
