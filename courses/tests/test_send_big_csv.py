"""Unit tests for the direct-SES big-CSV sender (pure functions only).

SMTP delivery itself is exercised by hand with --dry-run plus a single
real send to the operator; see scripts/send_big_csv.py.
"""

import csv
import io

from django.test import SimpleTestCase

from scripts.send_big_csv import (
    FLAT_FIELDS,
    build_message,
    flatten,
    rows_to_csv_text,
)
from scripts.send_campaign_export import build_body, build_subject
from scripts.genmedia_full_export import (
    ExportError,
    build_relay_command,
    split_recipients as export_split,
)


def row(**overrides):
    base = {
        "id": 1,
        "email": "a@example.com",
        "name": "Ann",
        "company_name": "Acme",
        "campaign": "camp",
        "course": "course",
        "country": "Germany",
        "region": "Europe",
        "ukraine_region": "",
        "role": "student_stem",
        "role_display": "Student (STEM)",
        "comment": "hello",
        "status": "approved",
        "created_at": "2026-11-06T00:00:00+00:00",
    }
    base.update(overrides)
    return base


class FlattenTestCase(SimpleTestCase):
    def test_newlines_become_spaces(self):
        self.assertEqual(flatten("a\nb\r\nc\rd"), "a b c d")

    def test_none_becomes_empty(self):
        self.assertEqual(flatten(None), "")


class RowsToCsvTestCase(SimpleTestCase):
    def test_multiline_comments_stay_on_one_physical_line(self):
        text = rows_to_csv_text(
            [row(id=1, comment="line1\nline2"), row(id=2, comment="plain")]
        )
        self.assertEqual(len(text.splitlines()), 3)
        parsed = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["comment"], "line1 line2")
        self.assertEqual(parsed[1]["email"], "a@example.com")

    def test_header_covers_all_participant_fields(self):
        text = rows_to_csv_text([row()])
        self.assertEqual(text.splitlines()[0], ",".join(FLAT_FIELDS))


class BuildMessageTestCase(SimpleTestCase):
    def test_recipients_subject_and_single_attachment(self):
        import tempfile

        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w", encoding="utf-8"
        ) as handle:
            handle.write("id,email\n1,a@example.com\n")
            path = handle.name
        message = build_message(
            "noreply@datatalks.club",
            ["me@example.com", "peer@example.com"],
            "Subject here",
            "Body here.",
            [path],
        )
        self.assertEqual(message["To"], "me@example.com, peer@example.com")
        self.assertEqual(message["Subject"], "Subject here")
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].get_filename().endswith(".csv"))


class CampaignExportTextTestCase(SimpleTestCase):
    def test_subject_and_body_carry_counts(self):
        counts = {"approved": 325, "pending": 273, "rejected": 27}
        self.assertEqual(
            build_subject(625),
            "Genmedia registrations so far: 625 (full CSV attached)",
        )
        body = build_body(625, counts, "2026-11-06")
        for fragment in ("625 registrations", "325 approved",
                         "273 pending", "27 rejected", "2026-11-06",
                         "single CSV file"):
            self.assertIn(fragment, body)


class FullExportCommandTestCase(SimpleTestCase):
    def test_single_call_single_recipient_with_one_attachment(self):
        command = build_relay_command(
            'relay', 'https://relay.example.com', 'KEY',
            ['misha@example.com'],
            'Subject', 'Body', 'idem-1', ['/tmp/x.csv'],
        )
        self.assertEqual(command[:4], ['relay', 'send', '--url', 'https://relay.example.com'])
        self.assertEqual(command.count('--to'), 1)
        self.assertIn('misha@example.com', command)
        self.assertEqual(command.count('--attach'), 1)
        self.assertIn('/tmp/x.csv', command)
        self.assertEqual(command.count('send'), 1)

    def test_rejects_multiple_recipients_or_attachments(self):
        with self.assertRaisesRegex(ExportError, "exactly one recipient"):
            build_relay_command(
                'relay', 'https://relay.example.com', 'KEY',
                ['one@example.com', 'two@example.com'],
                'Subject', 'Body', 'idem-1', ['/tmp/x.csv'],
            )
        with self.assertRaisesRegex(ExportError, "exactly one attachment"):
            build_relay_command(
                'relay', 'https://relay.example.com', 'KEY',
                ['one@example.com'], 'Subject', 'Body', 'idem-1',
                ['/tmp/x.csv', '/tmp/y.csv'],
            )

    def test_export_recipient_split(self):
        self.assertEqual(
            export_split('a@example.com, b@example.com'),
            ['a@example.com', 'b@example.com'],
        )
