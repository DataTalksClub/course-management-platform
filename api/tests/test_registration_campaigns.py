from unittest.mock import patch

from courses.models import CourseRegistration

from .registration_campaign_base import RegistrationCampaignAPITestBase


class RegistrationCampaignAPITestCase(RegistrationCampaignAPITestBase):
    def test_create_and_patch_registration_campaign(self):
        create_payload = {
            "slug": "llm-zoomcamp",
            "title": "LLM Zoomcamp",
            "edition_label": "2026 cohort",
            "current_course": self.course.slug,
            "marketing_markdown": "Register now",
        }
        response = self.post_campaign(self.client, create_payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "llm-zoomcamp")
        self.assertEqual(data["current_course"], self.course.slug)

        patch_payload = {
            "current_course": None,
        }
        response = self.patch_campaign(self.client, patch_payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["current_course"])

    def test_registration_campaign_registrations_stats(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)
        registration.role = CourseRegistration.Role.DATA_ENGINEER
        registration.save()

        url = self.campaign_registrations_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stats"]["total"], 1)
        self.assertEqual(data["stats"]["by_region"][0]["value"], "Europe")
        self.assertEqual(
            data["registrations"][0]["email"],
            "student@example.com",
        )
        self.assertEqual(
            data["registrations"][0]["company_name"],
            "Acme Data",
        )

    @patch(
        "api.views.registration_campaign_registration_mutations."
        "sync_registration_to_datamailer"
    )
    def test_bulk_create_registrations(self, sync_datamailer):
        campaign = self.create_campaign()
        payload = {
            "registrations": [
                {
                    "email": "Renu@Example.com",
                    "name": "Renu",
                    "country": "India",
                    "role": CourseRegistration.Role.ML_ENGINEER,
                },
                {
                    "email": "invalid-email",
                },
                {
                    "email": "kim@example.com",
                    "country": "Not A Real Country",
                },
            ],
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_registrations(self.client, payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["errors"], 2)

        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.campaign, campaign)
        self.assertEqual(registration.course, self.course)
        self.assertEqual(registration.email, "renu@example.com")
        self.assertEqual(registration.region, "Asia")
        sync_datamailer.assert_called_once_with(registration)

        results_by_status = {}
        for result in data["results"]:
            results_by_status.setdefault(result["status"], []).append(result)
        self.assertEqual(len(results_by_status["created"]), 1)
        self.assertEqual(len(results_by_status["error"]), 2)
        self.assertIn("email", results_by_status["error"][0]["errors"])
        self.assertIn("country", results_by_status["error"][1]["errors"])

    @patch(
        "api.views.registration_campaign_registration_mutations."
        "sync_registration_to_datamailer"
    )
    def test_bulk_create_registrations_skips_existing(self, sync_datamailer):
        campaign = self.create_campaign()
        self.create_registration(campaign)
        payload = {
            "registrations": [
                {"email": "student@example.com", "name": "Duplicate"},
            ],
        }

        response = self.post_registrations(self.client, payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        sync_datamailer.assert_not_called()

    def test_get_registration_detail(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)

        response = self.client.get(self.registration_detail_url(registration.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], registration.id)
        self.assertEqual(data["country"], "Germany")

    def test_patch_registration_country_updates_region(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)
        registration.country = "United States of America"
        registration.region = "North America"
        registration.save()

        payload = {"country": "United States"}
        response = self.patch_registration(
            self.client, registration.id, payload
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["country"], "United States")
        self.assertEqual(data["region"], "North America")

        registration.refresh_from_db()
        self.assertEqual(registration.country, "United States")
        self.assertEqual(registration.region, "North America")

    def test_patch_registration_rejects_invalid_country(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)

        payload = {"country": "Not A Real Country"}
        response = self.patch_registration(
            self.client, registration.id, payload
        )

        self.assertEqual(response.status_code, 400)
        registration.refresh_from_db()
        self.assertEqual(registration.country, "Germany")

    def test_patch_registration_rejects_unknown_field(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)

        payload = {"email": "changed@example.com"}
        response = self.patch_registration(
            self.client, registration.id, payload
        )

        self.assertEqual(response.status_code, 400)

    def test_approve_batch_approves_pending_and_queues_emails(self):
        from courses.models.application_notification import (
            ApplicationNotification,
        )

        campaign = self.create_campaign()
        first = self.create_registration(campaign)
        second = self.create_registration(campaign, email="second@example.com")

        response = self.post_approve_batch(
            self.client, {"ids": [first.id, second.id]}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            sorted(item["id"] for item in data["approved"]),
            sorted([first.id, second.id]),
        )
        self.assertEqual(data["skipped"], [])
        for registration_id in (first.id, second.id):
            registration = CourseRegistration.objects.get(
                id=registration_id
            )
            self.assertEqual(
                registration.status, CourseRegistration.Status.APPROVED
            )
            self.assertIsNotNone(registration.auto_approved_at)
            self.assertTrue(
                ApplicationNotification.objects.filter(
                    registration=registration,
                    template_key="application-approved",
                ).exists()
            )

    def test_approve_batch_is_idempotent(self):
        from courses.models.application_notification import (
            ApplicationNotification,
        )

        campaign = self.create_campaign()
        registration = self.create_registration(campaign)

        first = self.post_approve_batch(
            self.client, {"ids": [registration.id]}
        )
        self.assertEqual(first.status_code, 200)
        count = ApplicationNotification.objects.filter(
            registration=registration
        ).count()

        second = self.post_approve_batch(
            self.client, {"ids": [registration.id]}
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["approved"][0]["id"], registration.id)
        self.assertEqual(
            ApplicationNotification.objects.filter(
                registration=registration
            ).count(),
            count,
        )

    def test_approve_batch_skips_unknown_and_non_pending(self):
        campaign = self.create_campaign()
        pending = self.create_registration(campaign)
        rejected = self.create_registration(campaign, email="rejected@example.com")
        rejected.status = CourseRegistration.Status.REJECTED
        rejected.save(update_fields=["status", "updated_at"])

        response = self.post_approve_batch(
            self.client, {"ids": [pending.id, rejected.id, 999999]}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            [item["id"] for item in data["approved"]], [pending.id]
        )
        self.assertEqual(
            [(item["id"], item["reason"]) for item in data["skipped"]],
            [
                (rejected.id, "unexpected-status-rejected"),
                (999999, "not-found"),
            ],
        )

    def test_approve_batch_rejects_over_100_ids(self):
        campaign = self.create_campaign()
        self.create_registration(campaign)

        response = self.post_approve_batch(
            self.client, {"ids": list(range(1, 102))}
        )

        self.assertEqual(response.status_code, 400)

    def test_approve_batch_requires_staff(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)

        response = self.post_approve_batch(
            self.non_staff_client(), {"ids": [registration.id]}
        )

        self.assertEqual(response.status_code, 403)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, CourseRegistration.Status.PENDING
        )

    def test_registrations_list_filters_by_status(self):
        campaign = self.create_campaign()
        pending = self.create_registration(campaign)
        approved = self.create_registration(campaign, email="approved@example.com")
        approved.status = CourseRegistration.Status.APPROVED
        approved.save(update_fields=["status", "updated_at"])

        response = self.client.get(
            self.campaign_registrations_url() + "?status=pending"
        )

        self.assertEqual(response.status_code, 200)
        ids = [
            item["id"]
            for item in response.json()["registrations"]
        ]
        self.assertIn(pending.id, ids)
        self.assertNotIn(approved.id, ids)
