"""Reviewer custom message on application decision emails.

Approving (or rejecting) queues an applicant email. The reviewer can attach
an optional free-text message (e.g. promoting today's workshop); it is
stored in the queued notification context and rendered by the Relay
template. Empty message means a plain decision email.
"""

from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from courses.models import ApplicationNotification, CourseRegistration
from courses.registration_wall import approve_registration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


@override_settings(
    RELAY_URL="https://relay.example.com",
    RELAY_API_KEY="test-key",
    RELAY_CLIENT="dtc-courses",
    RELAY_AUDIENCE="dtc-courses",
)
class ApplicationCustomMessageTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save()
        self.staff = CustomUser.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="test",
            is_staff=True,
        )

    def create_pending(self, email="applicant@example.com"):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email=email,
            name="Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )

    def decide_url(self):
        return reverse(
            "cadmin_campaign_registration_decide",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    def test_approve_without_message_queues_empty_custom_message(self):
        registration = self.create_pending()
        approve_registration(registration)
        notification = ApplicationNotification.objects.get(
            registration=registration
        )
        self.assertEqual(notification.context["custom_message"], "")

    def test_approve_with_message_stores_it_in_context(self):
        registration = self.create_pending()
        approve_registration(
            registration,
            custom_message="Join the workshop today at 18:00!",
        )
        notification = ApplicationNotification.objects.get(
            registration=registration
        )
        self.assertEqual(
            notification.context["custom_message"],
            "Join the workshop today at 18:00!",
        )

    def test_cadmin_approve_with_message(self):
        registration = self.create_pending()
        self.client.force_login(self.staff)
        response = self.client.post(
            self.decide_url(),
            {
                "registration_id": registration.pk,
                "action": "approve",
                "custom_message": "Workshop today at 18:00!",
            },
        )
        self.assertEqual(response.status_code, 302)
        notification = ApplicationNotification.objects.get(
            registration=registration
        )
        self.assertEqual(
            notification.context["custom_message"],
            "Workshop today at 18:00!",
        )

    def test_cadmin_reject_with_message(self):
        registration = self.create_pending()
        self.client.force_login(self.staff)
        response = self.client.post(
            self.decide_url(),
            {
                "registration_id": registration.pk,
                "action": "reject",
                "custom_message": "Try the next cohort.",
            },
        )
        self.assertEqual(response.status_code, 302)
        notification = ApplicationNotification.objects.get(
            registration=registration,
            template_key="application-rejected",
        )
        self.assertEqual(
            notification.context["custom_message"], "Try the next cohort."
        )

    def test_bulk_approve_all_pending_with_shared_message(self):
        for i in range(3):
            self.create_pending(email=f"bulk{i}@example.com")
        self.client.force_login(self.staff)
        response = self.client.post(
            self.decide_url(),
            {
                "action": "approve_all_pending",
                "custom_message": "Workshop today at 18:00!",
            },
        )
        self.assertEqual(response.status_code, 302)
        notifications = ApplicationNotification.objects.filter(
            template_key="application-approved"
        )
        self.assertEqual(notifications.count(), 3)
        for notification in notifications:
            self.assertEqual(
                notification.context["custom_message"],
                "Workshop today at 18:00!",
            )

    def test_bulk_approve_skips_genmedia_excluded(self):
        from courses.genmedia_policy import CAMPAIGN_SLUG
        from courses.models import RegistrationCampaign

        campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        for email, country in (
            ("eligible@example.com", "Germany"),
            ("excluded@example.com", "Russia"),
        ):
            CourseRegistration.objects.create(
                campaign=campaign,
                course=campaign.current_course,
                email=email,
                name="Bulk",
                country=country,
                region="Europe",
                role=CourseRegistration.Role.DATA_ENGINEER,
            )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "cadmin_campaign_registration_decide",
                kwargs={"campaign_slug": campaign.slug},
            ),
            {
                "action": "approve_all_pending",
                "custom_message": "Workshop today at 18:00!",
            },
        )
        self.assertEqual(response.status_code, 302)
        approved = ApplicationNotification.objects.filter(
            template_key="application-approved"
        )
        self.assertEqual(approved.count(), 1)
        self.assertEqual(
            approved.get().recipient, "eligible@example.com"
        )
        excluded = CourseRegistration.objects.get(
            email="excluded@example.com"
        )
        self.assertEqual(
            excluded.status, CourseRegistration.Status.PENDING
        )

    def test_bulk_reject_excluded_with_location_message(self):
        from courses.decision_messages import REJECTION_MESSAGE_LOCATION
        from courses.genmedia_policy import CAMPAIGN_SLUG
        from courses.models import RegistrationCampaign

        campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        for email, country in (
            ("eligible@example.com", "Germany"),
            ("excluded@example.com", "Russia"),
        ):
            CourseRegistration.objects.create(
                campaign=campaign,
                course=campaign.current_course,
                email=email,
                name="Bulk",
                country=country,
                region="Europe",
                role=CourseRegistration.Role.DATA_ENGINEER,
            )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                "cadmin_campaign_registration_decide",
                kwargs={"campaign_slug": campaign.slug},
            ),
            {"action": "reject_excluded"},
        )
        self.assertEqual(response.status_code, 302)
        rejected = ApplicationNotification.objects.filter(
            template_key="application-rejected"
        )
        self.assertEqual(rejected.count(), 1)
        self.assertEqual(rejected.get().recipient, "excluded@example.com")
        self.assertEqual(
            rejected.get().context["custom_message"],
            REJECTION_MESSAGE_LOCATION,
        )
        eligible = CourseRegistration.objects.get(
            email="eligible@example.com"
        )
        self.assertEqual(
            eligible.status, CourseRegistration.Status.PENDING
        )

    def test_list_page_prefills_launch_message(self):
        from django.urls import reverse

        self.client.force_login(self.staff)
        response = self.client.get(
            reverse(
                "cadmin_campaign_registrations",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "youtube.com/@DataTalksClub")

    def test_decision_templates_render_custom_message(self):
        from course_management.relay.application_templates import (
            APPLICATION_TEMPLATES,
        )

        for key in ("application-approved", "application-rejected"):
            draft = APPLICATION_TEMPLATES[key]
            # Optional: empty messages must validate, so the field is
            # not in required_context. It stays in the shared example
            # pool for template authors.
            field_names = [
                field["name"] for field in draft["required_context"]
            ]
            self.assertNotIn("custom_message", field_names)
            self.assertIn("custom_message", draft["html_body"])
            self.assertIn("custom_message", draft["text_body"])


class DecisionCustomMessageMigrationTests(TransactionTestCase):
    def test_old_queued_rows_gain_empty_custom_message(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        before = ("courses", "0062_answer_ans_question_correct_idx_and_more")
        after = ("courses", "0063_backfill_decision_custom_message")
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([before])
            old_apps = executor.loader.project_state([before]).apps
            Course = old_apps.get_model("courses", "Course")
            Campaign = old_apps.get_model(
                "courses", "RegistrationCampaign"
            )
            Registration = old_apps.get_model(
                "courses", "CourseRegistration"
            )
            Notification = old_apps.get_model(
                "courses", "ApplicationNotification"
            )
            course = Course.objects.create(
                slug="legacy-decision", title="Legacy"
            )
            campaign = Campaign.objects.create(
                slug="legacy-decision",
                title="Legacy",
                current_course=course,
            )
            registration = Registration.objects.create(
                campaign=campaign,
                course=course,
                email="legacy@example.com",
                email_normalized="legacy@example.com",
                name="Legacy",
                country="Germany",
                region="Europe",
                role="ml_engineer",
            )
            notification = Notification.objects.create(
                registration=registration,
                decision_sequence=1,
                template_key="application-approved",
                recipient="legacy@example.com",
                context={"name": "Legacy"},
            )
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            new_apps = executor.loader.project_state([after]).apps
            Notification = new_apps.get_model(
                "courses", "ApplicationNotification"
            )
            row = Notification.objects.get(pk=notification.pk)
            self.assertEqual(row.context["custom_message"], "")
            self.assertEqual(row.context["name"], "Legacy")
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class CustomMessageFormatTests(RegistrationCampaignBase):
    def test_empty_message_renders_nothing(self):
        from course_management.relay.message_format import (
            custom_message_html,
        )

        self.assertEqual(custom_message_html(""), "")
        self.assertEqual(custom_message_html("   \n  "), "")

    def test_paragraphs_bold_and_links(self):
        from course_management.relay.message_format import (
            custom_message_html,
        )

        rendered = custom_message_html(
            "**Hello!** See https://example.com/a?b=1.\n\nSecond line here."
        )
        self.assertIn("<p><strong>Hello!</strong> See ", rendered)
        self.assertIn(
            '<a href="https://example.com/a?b=1">'
            "https://example.com/a?b=1</a>.",
            rendered,
        )
        self.assertIn("<p>Second line here.</p>", rendered)

    def test_html_is_escaped(self):
        from course_management.relay.message_format import (
            custom_message_html,
        )

        rendered = custom_message_html('<script>alert("x")</script>')
        self.assertNotIn("<script>", rendered)
        self.assertIn(
            "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", rendered
        )

    def test_context_carries_formatted_html(self):
        from course_management.relay.application_notifications import (
            notification_context,
        )

        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="format@example.com",
            name="Format",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        context = notification_context(
            registration, custom_message="**Hi!** See https://example.com."
        )
        self.assertEqual(
            context["custom_message_html"],
            '<p><strong>Hi!</strong> See '
            '<a href="https://example.com">https://example.com</a>.</p>',
        )
        empty = notification_context(registration)
        self.assertEqual(empty["custom_message_html"], "")
        self.assertEqual(empty["custom_message"], "")

    def test_markdown_named_link(self):
        from course_management.relay.message_format import (
            custom_message_html,
            custom_message_text,
        )

        rendered = custom_message_html(
            "Come say hi in [#course-ai-mediagen](https://example.com/c) today."
        )
        self.assertIn(
            '<a href="https://example.com/c">#course-ai-mediagen</a>',
            rendered,
        )
        self.assertNotIn("example.com/c\">https://example.com/c<", rendered)
        self.assertEqual(
            custom_message_text(
                "Come say hi in [#course-ai-mediagen](https://example.com/c)."
            ),
            "Come say hi in #course-ai-mediagen (https://example.com/c).",
        )

    def test_rejected_template_has_audit_block(self):
        from course_management.relay.application_templates import (
            APPLICATION_TEMPLATES,
        )

        draft = APPLICATION_TEMPLATES["application-rejected"]
        self.assertIn("Audit the course for free", draft["html_body"])
        self.assertIn("github_url", draft["html_body"])
        self.assertIn("audit the course for free", draft["text_body"])

    def test_context_carries_github_url(self):
        from course_management.relay.application_notifications import (
            notification_context,
        )

        self.course.github_repo_url = "https://github.com/example/repo"
        self.course.save(update_fields=["github_repo_url"])
        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="github@example.com",
            name="Github",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        context = notification_context(registration)
        self.assertEqual(
            context["github_url"], "https://github.com/example/repo"
        )
