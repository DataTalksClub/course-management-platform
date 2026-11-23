"""End-to-end read path of scripts/genmedia_full_export.py.

The script's HTTP calls are routed into the real CMP API view through the
Django test client, against a fixture with more than 500 approved
registrations. Relay is mocked and asserted unused: nothing is sent.
"""

import csv
import io
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, CourseRegistration, RegistrationCampaign
from scripts.genmedia_full_export import (
    REPORT_FIELDS,
    ExportError,
    fetch_all,
    main,
    shareable_rows,
)
from scripts.send_campaign_export import IncompleteExportError

CAMPAIGN = "production-ai-agents-generative-media"
APPROVED_SHARED = 1197
APPROVED_WITHHELD = 4
PENDING = 30
REJECTED = 12
BASE_TIME = datetime(2026, 10, 22, 4, 0, tzinfo=timezone.utc)
ROLES = [choice.value for choice in CourseRegistration.Role]
COUNTRIES = ["India", "United States", "Germany", "Ukraine"]

# Column order of the 23 Nov 2026 corrected file approved for Mikhail.
SCHEMA_23_NOV = (
    "id,email,name,company_name,linkedin_url,github_url,status,created_at,"
    "auto_approved_at,accepted_nebius_sharing,country,role"
).split(",")
# The 13 Nov 2026 file: all statuses, no consent column, no profile links.
SCHEMA_13_NOV = (
    "id,email,name,company_name,campaign,course,country,region,"
    "ukraine_region,role,role_display,comment,status,utm_source,utm_medium,"
    "utm_campaign,utm_content,utm_term,landing_referrer,created_at"
).split(",")


class _ClientResponse:
    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._response.json()


class GenmediaFullExportReadPathTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = CustomUser.objects.create(
            username="ops", email="ops@example.com", is_staff=True
        )
        cls.token = Token.objects.create(user=user).key
        course = Course.objects.create(
            slug="genmedia-2026", title="Genmedia", description="Genmedia"
        )
        # A data migration already seeds the Genmedia campaign.
        campaign, _ = RegistrationCampaign.objects.update_or_create(
            slug=CAMPAIGN,
            defaults={"title": "Genmedia", "current_course": course},
        )
        CourseRegistration.objects.filter(campaign=campaign).delete()
        plan = (
            [("approved", True)] * APPROVED_SHARED
            + [("approved", False)] * APPROVED_WITHHELD
            + [("pending", True)] * PENDING
            + [("rejected", True)] * REJECTED
        )
        registrations = []
        for index, (status, consent) in enumerate(plan):
            email = f"person{index}@example.com"
            registrations.append(
                CourseRegistration(
                    campaign=campaign,
                    course=course,
                    email=email,
                    email_normalized=email,
                    name=f"Person {index}",
                    company_name="Acme, Inc.",
                    country=COUNTRIES[index % len(COUNTRIES)],
                    role=ROLES[index % len(ROLES)],
                    comment="line one\nline two",
                    linkedin_url=f"https://linkedin.com/in/p{index}",
                    status=status,
                    accepted_nebius_sharing=consent,
                    auto_approved_at=(
                        BASE_TIME if status == "approved" else None
                    ),
                )
            )
        CourseRegistration.objects.bulk_create(registrations)
        # Pairs share a created_at so pagination must rely on the id
        # tie-breaker to stay stable.
        for registration in CourseRegistration.objects.all():
            CourseRegistration.objects.filter(pk=registration.pk).update(
                created_at=BASE_TIME + timedelta(minutes=registration.pk // 2)
            )
        cls.shared_ids = set(
            CourseRegistration.objects.filter(
                status="approved", accepted_nebius_sharing=True
            ).values_list("id", flat=True)
        )

    def setUp(self):
        self.client = Client()
        self.requests = []
        self.export_dir = tempfile.mkdtemp(prefix="genmedia-export-test-")

    def fake_get(self, url, params=None, headers=None, timeout=None):
        self.requests.append(dict(params or {}))
        path = url.split("https://cmp.example", 1)[1]
        response = self.client.get(
            path, params or {}, HTTP_AUTHORIZATION=headers["Authorization"]
        )
        return _ClientResponse(response)

    def env(self):
        return {
            "CMP_BASE_URL": "https://cmp.example",
            "CMP_API_TOKEN": self.token,
            "CAMPAIGN_SLUG": CAMPAIGN,
            "GENMEDIA_EXPORT_DIR": self.export_dir,
            "GENMEDIA_WEEKLY_REPORT_TO": "mnrozhkov@nebius.com",
        }

    def test_fixture_exceeds_one_api_page(self):
        approved = CourseRegistration.objects.filter(status="approved")
        self.assertGreater(approved.count(), 500 * 2)

    @patch("scripts.genmedia_full_export.subprocess.run")
    def test_dry_run_exports_every_consented_approved_row(self, send_command):
        with patch.dict(os.environ, self.env()), patch(
            "scripts.send_campaign_export.requests.get", self.fake_get
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            result = main(
                ["--dry-run"],
                now=datetime(2026, 11, 23, 15, 0, tzinfo=ZoneInfo("Europe/Berlin")),
            )

        self.assertEqual(result, 0, stdout.getvalue())
        send_command.assert_not_called()
        self.assertIn("no email sent", stdout.getvalue())
        self.assertIn(
            f"fetched {APPROVED_SHARED + APPROVED_WITHHELD} approved (complete); "
            f"{APPROVED_SHARED} shareable, {APPROVED_WITHHELD} withheld",
            stdout.getvalue(),
        )
        offsets = [r["offset"] for r in self.requests if "offset" in r]
        self.assertEqual(offsets, [0, 500, 1000])

        path = os.path.join(
            self.export_dir, "genmedia-weekly-report-2026-11-23.csv"
        )
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertEqual(len(text.splitlines()), APPROVED_SHARED + 1)
        rows = list(csv.DictReader(io.StringIO(text)))

        self.assertEqual(list(rows[0].keys()), list(REPORT_FIELDS))
        self.assertEqual(list(REPORT_FIELDS), SCHEMA_23_NOV)
        self.assertIn("country", REPORT_FIELDS)
        self.assertIn("role", REPORT_FIELDS)
        self.assertEqual({int(row["id"]) for row in rows}, self.shared_ids)
        self.assertEqual(len(rows), APPROVED_SHARED)
        self.assertEqual({row["status"] for row in rows}, {"approved"})
        self.assertEqual(
            {row["accepted_nebius_sharing"] for row in rows}, {"True"}
        )
        self.assertTrue(all(row["country"] in COUNTRIES for row in rows))
        self.assertTrue(all(row["role"] in ROLES for row in rows))
        keys = [(row["created_at"], int(row["id"])) for row in rows]
        self.assertEqual(keys, sorted(keys))

    def test_schema_differs_from_13_nov_only_as_agreed(self):
        # Kept from 13 Nov: identity, company, country, role, status, date.
        self.assertEqual(
            [f for f in SCHEMA_13_NOV if f in REPORT_FIELDS],
            ["id", "email", "name", "company_name", "country", "role",
             "status", "created_at"],
        )
        # Free-text comments and attribution are no longer shared.
        for dropped in ("comment", "utm_source", "landing_referrer", "region"):
            self.assertNotIn(dropped, REPORT_FIELDS)

    def test_legacy_api_without_pagination_fails_closed(self):
        def legacy_get(url, params=None, headers=None, timeout=None):
            response = self.fake_get(url, params, headers, timeout)
            payload = response.json()
            payload.pop("count")
            response.json = lambda: payload
            return response

        with patch("scripts.send_campaign_export.requests.get", legacy_get):
            with self.assertRaises(IncompleteExportError):
                fetch_all("https://cmp.example", self.token, CAMPAIGN)

    def test_rows_without_consent_field_fail_closed(self):
        with self.assertRaisesRegex(ExportError, "accepted_nebius_sharing"):
            shareable_rows([{"id": 1, "status": "approved"}])
