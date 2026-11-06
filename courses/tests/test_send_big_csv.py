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
