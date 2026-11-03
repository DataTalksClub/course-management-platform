from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.urls import reverse

from accounts.models import CustomUser
from courses.genmedia_approval import (
    approval_due,
    approve_pending_registrations,
    maybe_run_scheduled_approval,
)
from courses.genmedia_policy import (
    AUTO_APPROVAL_HOUR,
    AUTO_APPROVAL_LIMIT,
    AUTO_APPROVAL_TIMEZONE,
    CAMPAIGN_SLUG,
    EXCLUDED_UKRAINE_REGIONS,
    RESTRICTED_COUNTRIES,
    RESTRICTED_ENTRIES,
    excluded_reason,
)
from courses.models import (
    CourseRegistration,
    GenmediaApprovalRun,
    RegistrationCampaign,
)
from courses.models.application_notification import ApplicationNotification
from courses.tests.registration_campaign_base import RegistrationCampaignBase


BERLIN = ZoneInfo("Europe/Berlin")


class GenmediaPolicyTests(RegistrationCampaignBase):
    def test_restricted_configuration_has_exact_nineteen_entries(self):
        self.assertEqual(
            RESTRICTED_ENTRIES,
            (
                "Belarus",
                "Benin",
                "Bolivia",
                "Cameroon",
                "China",
                "Costa Rica",
                "Crimea (Ukraine)",
                "Cuba",
                "DPR / LPR (Ukraine)",
                "Georgia",
                "Hong Kong",
                "Indonesia",
                "Iran",
                "Kyrgyzstan",
                "Moldova",
                "Nigeria",
                "North Korea",
                "Pakistan",
                "Russia",
            ),
        )
        self.assertEqual(len(RESTRICTED_ENTRIES), 19)
        self.assertNotIn("Ukraine", RESTRICTED_COUNTRIES)
        self.assertEqual(AUTO_APPROVAL_LIMIT, 2000)
        self.assertEqual(AUTO_APPROVAL_TIMEZONE, "Europe/Berlin")
        self.assertEqual(AUTO_APPROVAL_HOUR, 20)

    def test_region_policy_excludes_only_crimea_and_occupied_east(self):
        self.assertEqual(
            EXCLUDED_UKRAINE_REGIONS,
            {"crimea", "donetsk_occupied", "luhansk_occupied"},
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(country="Ukraine", ukraine_region="")
            ),
            "",
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(
                    country="Ukraine", ukraine_region="donetsk_occupied"
                )
            ),
            "Ukraine region",
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(
                    country="Ukraine", ukraine_region="luhansk_occupied"
                )
            ),
            "Ukraine region",
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(country="Ukraine", ukraine_region="crimea")
            ),
            "Ukraine region",
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(
                    country="Ukraine", ukraine_region="lviv"
                )
            ),
            "",
        )
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(country="Russia", ukraine_region="")
            ),
            "country",
        )
        # Case/whitespace-insensitive, like the free-text country combobox.
        self.assertEqual(
            excluded_reason(
                SimpleNamespace(country="  RUSSIA ", ukraine_region="")
            ),
            "country",
        )


class GenmediaNightlyApprovalTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        # Migration 0047 seeds this campaign; reuse it and point it at
        # the test course instead of creating a duplicate slug.
        self.campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        self.campaign.current_course = self.course
        self.campaign.is_active = True
        self.campaign.save(update_fields=["current_course", "is_active"])

    def registration(self, *, email, country, ukraine_region=""):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email=email,
            name="Test Applicant",
            country=country,
            region="",
            ukraine_region=ukraine_region,
            role=CourseRegistration.Role.ML_ENGINEER,
            status=CourseRegistration.Status.PENDING,
        )

    def berlin_evening(self, day):
        return datetime(day.year, day.month, day.day, 20, 5, tzinfo=BERLIN)

    def test_evening_run_approves_eligible_and_flags_excluded(self):
        from datetime import date

        eligible = self.registration(
            email="eligible@example.test",
            country="Ukraine",
            ukraine_region="lviv",
        )
        excluded_country = self.registration(
            email="country@example.test", country="Belarus"
        )
        excluded_region = self.registration(
            email="region@example.test",
            country="Ukraine",
            ukraine_region="crimea",
        )
        result = approve_pending_registrations(
            now=self.berlin_evening(date(2026, 11, 3))
        )

        self.assertTrue(result.ran)
        self.assertEqual(result.approved, 1)
        self.assertEqual(result.excluded, 2)
        self.assertFalse(result.stopped_at_limit)
        eligible.refresh_from_db()
        excluded_country.refresh_from_db()
        excluded_region.refresh_from_db()
        self.assertEqual(eligible.status, CourseRegistration.Status.APPROVED)
        self.assertIsNotNone(eligible.auto_approved_at)
        self.assertEqual(
            excluded_country.status, CourseRegistration.Status.PENDING
        )
        self.assertEqual(
            excluded_region.status, CourseRegistration.Status.PENDING
        )
        self.assertIsNone(excluded_country.auto_approved_at)
        self.assertIsNone(excluded_region.auto_approved_at)
        run = GenmediaApprovalRun.objects.get(date=date(2026, 11, 3))
        self.assertEqual(
            run.status, GenmediaApprovalRun.Status.COMPLETED
        )
        self.assertEqual(run.approved_count, 1)
        self.assertEqual(run.excluded_count, 2)
        self.assertEqual(eligible.genmedia_excluded_reason, "")
        self.assertEqual(excluded_country.genmedia_excluded_reason, "country")
        self.assertEqual(
            excluded_region.genmedia_excluded_reason, "Ukraine region"
        )

    def test_evening_run_sends_no_emails_to_registrants(self):
        self.registration(
            email="eligible@example.test",
            country="Germany",
        )
        self.registration(
            email="excluded@example.test", country="Iran"
        )
        from datetime import date

        notifications_before = ApplicationNotification.objects.count()
        result = approve_pending_registrations(
            now=self.berlin_evening(date(2026, 11, 3))
        )

        self.assertTrue(result.ran)
        self.assertEqual(result.approved, 1)
        self.assertEqual(
            ApplicationNotification.objects.count(), notifications_before
        )

    def test_morning_run_does_not_touch_pending_rows(self):
        from datetime import date

        pending = self.registration(
            email="pending@example.test", country="Germany"
        )
        morning = datetime(2026, 11, 3, 9, 5, tzinfo=BERLIN)

        self.assertFalse(approval_due(now=morning))
        result = approve_pending_registrations(now=morning)

        self.assertFalse(result.ran)
        self.assertEqual(result.approved, 0)
        pending.refresh_from_db()
        self.assertEqual(pending.status, CourseRegistration.Status.PENDING)
        self.assertFalse(
            GenmediaApprovalRun.objects.filter(
                date=date(2026, 11, 3)
            ).exists()
        )

    def test_single_run_per_berlin_day_across_dst(self):
        # Summer (CEST, UTC+2) and winter (CET, UTC+1) evenings both map
        # to the 20:00 Berlin hour; a second tick the same Berlin date is
        # already-done, never a second approval run.
        from datetime import date

        first = self.registration(
            email="first@example.test", country="Germany"
        )
        summer_evening = datetime(2026, 7, 1, 18, 5, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(approval_due(now=summer_evening))
        first_run = approve_pending_registrations(now=summer_evening)
        self.assertTrue(first_run.ran)
        self.assertEqual(first_run.approved, 1)

        second = self.registration(
            email="second@example.test", country="Germany"
        )
        later_same_berlin_date = datetime(
            2026, 7, 1, 18, 35, tzinfo=ZoneInfo("UTC")
        )
        self.assertFalse(approval_due(now=later_same_berlin_date))
        second_run = approve_pending_registrations(
            now=later_same_berlin_date
        )
        self.assertFalse(second_run.ran)
        self.assertEqual(second_run.reason, "already-done")
        second.refresh_from_db()
        self.assertEqual(second.status, CourseRegistration.Status.PENDING)

        winter_evening = datetime(2026, 1, 7, 19, 5, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(approval_due(now=winter_evening))
        winter_run = approve_pending_registrations(now=winter_evening)
        self.assertTrue(winter_run.ran)
        self.assertEqual(winter_run.approved, 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, CourseRegistration.Status.APPROVED)
        self.assertEqual(second.status, CourseRegistration.Status.APPROVED)
        self.assertEqual(
            GenmediaApprovalRun.objects.filter(
                date=date(2026, 7, 1)
            ).count(),
            1,
        )

    def test_limit_stops_approval_and_preserves_pending_rows(self):
        from datetime import date

        pending = self.registration(
            email="pending@example.test", country="Germany"
        )
        CourseRegistration.objects.filter(
            email_normalized="already@example.test"
        ).delete()
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="already@example.test",
            name="Already Approved",
            country="Germany",
            region="",
            role=CourseRegistration.Role.ML_ENGINEER,
            status=CourseRegistration.Status.APPROVED,
        )

        with patch(
            "courses.genmedia_approval.AUTO_APPROVAL_LIMIT", 2
        ):
            result = approve_pending_registrations(
                now=self.berlin_evening(date(2026, 11, 3))
            )

        self.assertTrue(result.ran)
        self.assertTrue(result.stopped_at_limit)
        self.assertEqual(result.approved, 0)
        pending.refresh_from_db()
        self.assertEqual(pending.status, CourseRegistration.Status.PENDING)
        run = GenmediaApprovalRun.objects.get(date=date(2026, 11, 3))
        self.assertEqual(
            run.status, GenmediaApprovalRun.Status.STOPPED_AT_LIMIT
        )

    def test_scheduled_hook_returns_none_when_not_due(self):
        morning = datetime(2026, 11, 3, 9, 5, tzinfo=BERLIN)
        self.assertIsNone(maybe_run_scheduled_approval(now=morning))

    def test_scheduled_hook_never_raises(self):
        from datetime import date

        with patch(
            "courses.genmedia_approval.approve_pending_registrations",
            side_effect=RuntimeError("boom"),
        ):
            result = maybe_run_scheduled_approval(
                now=self.berlin_evening(date(2026, 11, 3))
            )
        self.assertIsNotNone(result)
        self.assertFalse(result.ran)
        self.assertEqual(result.reason, "failed")


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class GenmediaRegistrationFormTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        self.campaign.current_course = self.course
        self.campaign.is_active = True
        self.campaign.save(update_fields=["current_course", "is_active"])
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])

    def post_payload(self, **overrides):
        payload = self.registration_payload()
        # Wall (application-review) forms require experience + consent.
        payload["experience"] = "3 years building ML systems"
        payload.update(overrides)
        with patch(
            "courses.views.registration.send_registration_confirmation_email"
        ), patch(
            "courses.views.registration.sync_registration_to_relay"
        ), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.campaign_url(), payload)

    def test_ukraine_region_field_rendered_for_genmedia_campaign(self):
        response = self.client.get(self.campaign_url())
        self.assertContains(
            response, "Which part of Ukraine do you live in?"
        )
        self.assertContains(response, "Donetsk Oblast (DPR-occupied)")
        self.assertContains(response, "data-ukraine-region-input")

    def test_ukraine_region_field_hidden_for_other_campaigns(self):
        other_url = reverse(
            "registration_campaign",
            kwargs={"campaign_slug": "llm-zoomcamp"},
        )
        response = self.client.get(other_url)
        self.assertNotContains(
            response, "Which part of Ukraine do you live in?"
        )
        self.assertNotContains(response, "data-ukraine-region-input")

    def test_ukraine_without_region_is_rejected(self):
        response = self.post_payload(country="Ukraine")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 0)
        self.assertContains(response, "Select your region or oblast.")

    def test_ukraine_region_is_required_and_persisted(self):
        response = self.post_payload(
            country="Ukraine", ukraine_region="lviv"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.ukraine_region, "lviv")
        self.assertEqual(registration.region, "Europe")

    def test_non_ukraine_clears_stale_region(self):
        response = self.post_payload(
            country="Germany", ukraine_region="lviv"
        )
        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.ukraine_region, "")

    def test_non_ukraine_registers_without_region(self):
        response = self.post_payload(country="Germany")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)


class GenmediaPreviewTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        self.campaign.current_course = self.course
        self.campaign.is_active = True
        self.campaign.save(update_fields=["current_course", "is_active"])
        self.preview_url = reverse(
            "cadmin_campaign_genmedia_preview",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    def make_approved(self):
        approved = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="approved@example.test",
            name="Approved Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.ML_ENGINEER,
            status=CourseRegistration.Status.APPROVED,
        )
        CourseRegistration.objects.filter(pk=approved.pk).update(
            auto_approved_at=datetime(
                2026, 11, 3, 19, 5, tzinfo=ZoneInfo("UTC")
            )
        )
        approved.refresh_from_db()
        return approved

    def make_staff(self):
        staff = CustomUser.objects.create_user(
            username="preview-staff",
            email="staff@example.com",
            password="test",
            is_staff=True,
        )
        return staff

    def test_preview_requires_staff(self):
        self.make_approved()
        response = self.client.get(self.preview_url)
        self.assertEqual(response.status_code, 302)

        user = CustomUser.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="test",
        )
        self.client.force_login(user)
        response = self.client.get(self.preview_url)
        self.assertEqual(response.status_code, 302)

    def test_preview_visible_to_staff_with_csv_download(self):
        self.make_approved()
        self.client.force_login(self.make_staff())

        response = self.client.get(self.preview_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "approved@example.test")
        self.assertContains(response, "no auto-send")

        csv_response = self.client.get(
            self.preview_url, {"format": "csv"}
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(
            "approved@example.test",
            csv_response.content.decode("utf-8"),
        )

    def test_preview_rejects_other_campaigns(self):
        self.client.force_login(self.make_staff())
        other_url = reverse(
            "cadmin_campaign_genmedia_preview",
            kwargs={"campaign_slug": "llm-zoomcamp"},
        )
        response = self.client.get(other_url)
        self.assertEqual(response.status_code, 404)

    def test_registrations_list_flags_excluded_for_genmedia(self):
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="flagged@example.test",
            name="Flagged Applicant",
            country="Belarus",
            region="Europe",
            role=CourseRegistration.Role.ML_ENGINEER,
        )
        self.client.force_login(self.make_staff())
        response = self.client.get(
            reverse(
                "cadmin_campaign_registrations",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Excluded: country")
        self.assertContains(response, "Nebius preview")
