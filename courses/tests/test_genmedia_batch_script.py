"""Unit tests for the hetzner evening batch script (pure functions only).

HTTP and datamailer sending are exercised against prod in the manual
first run; API behaviour itself is covered by api/tests.
"""

from django.test import SimpleTestCase

from scripts.genmedia_evening_batch import (
    build_csv,
    chunked,
    select_approvable,
)


def row(email, country, ukraine_region=""):
    return {
        "id": abs(hash(email)) % 10**6,
        "email": email,
        "name": "Test",
        "country": country,
        "ukraine_region": ukraine_region,
    }


class SelectApprovableTestCase(SimpleTestCase):
    def test_eligible_rows_approved(self):
        pending = [row("a@example.com", "Germany")]
        approvable, skipped = select_approvable(pending, total_count=10)
        self.assertEqual([r["email"] for r in approvable], ["a@example.com"])
        self.assertEqual(skipped, [])

    def test_restricted_country_skipped(self):
        pending = [
            row("ru@example.com", "Russia"),
            row("ok@example.com", "Germany"),
        ]
        approvable, skipped = select_approvable(pending, total_count=10)
        self.assertEqual([r["email"] for r in approvable], ["ok@example.com"])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0][1], "excluded-country")

    def test_occupied_ukraine_region_skipped(self):
        pending = [
            row("c@example.com", "Ukraine", ukraine_region="crimea"),
            row("l@example.com", "Ukraine", ukraine_region="lviv"),
        ]
        approvable, skipped = select_approvable(pending, total_count=10)
        self.assertEqual([r["email"] for r in approvable], ["l@example.com"])
        self.assertEqual(skipped[0][1], "excluded-Ukraine region")

    def test_cap_stops_approvals(self):
        pending = [row("a@example.com", "Germany")]
        approvable, skipped = select_approvable(pending, total_count=2000)
        self.assertEqual(approvable, [])
        self.assertEqual(skipped[0][1], "cap-reached")


class ChunkedTestCase(SimpleTestCase):
    def test_chunks_of_100(self):
        self.assertEqual(chunked(list(range(250)), 100), [list(range(100)), list(range(100, 200)), list(range(200, 250))])


class BuildCsvTestCase(SimpleTestCase):
    def test_header_and_rows(self):
        from datetime import date

        csv_text = build_csv(
            [row("a@example.com", "Germany")], date(2026, 11, 5)
        )
        lines = csv_text.strip().splitlines()
        self.assertEqual(
            lines[0], "name,email,country,ukraine_region,approved_at"
        )
        self.assertIn("a@example.com", lines[1])
        self.assertIn("2026-11-05", lines[1])


class SplitRecipientsTestCase(SimpleTestCase):
    def test_splits_commas_and_spaces(self):
        from scripts.genmedia_evening_batch import split_recipients

        self.assertEqual(
            split_recipients("a@x.com, b@y.com c@z.com"),
            ["a@x.com", "b@y.com", "c@z.com"],
        )
