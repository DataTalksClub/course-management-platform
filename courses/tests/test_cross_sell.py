import datetime
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from course_management.datamailer.payloads.registration_confirmations import (
    registration_confirmation_context,
    registration_confirmation_urls,
)
from course_management.relay.confirmation_reminders import reminder_action
from courses import cross_sell
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)
from courses.registration_confirmation import (
    confirm_registration_by_token,
    issue_confirmation_token,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class CrossSellBase(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        # Data migrations seed real campaigns; keep the rule tests exact.
        RegistrationCampaign.objects.exclude(pk=self.campaign.pk).delete()
        today = timezone.localdate()
        self.de = self.create_campaign(
            "de-zoomcamp", "Data Engineering Zoomcamp", today + datetime.timedelta(days=60)
        )
        self.ml = self.create_campaign(
            "ml-zoomcamp", "ML Zoomcamp", today + datetime.timedelta(days=30)
        )
        self.mlops = self.create_campaign(
            "mlops-zoomcamp", "MLOps Zoomcamp", today + datetime.timedelta(days=90)
        )
        self.next_cohort = RegistrationCampaign.objects.create(
            slug="ai-dev-tools", title="AI Dev Tools Zoomcamp"
        )

    def create_campaign(self, slug, title, start_date, **course_fields):
        course = Course.objects.create(
            slug=f"{slug}-2027",
            title=f"{title} 2027",
            start_date=start_date,
            **course_fields,
        )
        return RegistrationCampaign.objects.create(
            slug=slug,
            title=title,
            edition_label="2027 cohort",
            current_course=course,
        )

    def register(self, email="Student@Example.com"):
        return self.client.post(
            self.campaign_url(), self.registration_payload(email)
        )

    def source_registration(self):
        return CourseRegistration.objects.get(campaign=self.campaign)

    def suggested_slugs(self, **kwargs):
        return [
            suggestion.campaign.slug
            for suggestion in cross_sell.suggestions(self.campaign, **kwargs)
        ]


class SuggestionRuleTests(CrossSellBase):
    def test_fallback_orders_by_start_date_then_undated(self):
        self.assertEqual(
            self.suggested_slugs(limit=10),
            ["ml-zoomcamp", "de-zoomcamp", "mlops-zoomcamp", "ai-dev-tools"],
        )

    def test_curated_suggestions_come_first(self):
        self.campaign.suggested_campaigns.set([self.mlops, self.next_cohort])
        self.assertEqual(
            self.suggested_slugs(),
            ["mlops-zoomcamp", "ai-dev-tools", "ml-zoomcamp"],
        )

    def test_default_limit_is_three(self):
        self.assertEqual(len(self.suggested_slugs()), 3)

    def test_excludes_finished_inactive_and_flagged(self):
        Course.objects.filter(pk=self.ml.current_course_id).update(
            finished=True
        )
        RegistrationCampaign.objects.filter(pk=self.de.pk).update(
            is_active=False
        )
        RegistrationCampaign.objects.filter(pk=self.mlops.pk).update(
            exclude_from_suggestions=True
        )
        self.assertEqual(self.suggested_slugs(), ["ai-dev-tools"])

    @override_settings(CROSS_SELL_EXCLUDED_CAMPAIGNS=["ml-zoomcamp"])
    def test_settings_exclusion_list(self):
        self.assertNotIn("ml-zoomcamp", self.suggested_slugs(limit=10))

    def test_excludes_same_edition_campaign(self):
        RegistrationCampaign.objects.create(
            slug="llm-zoomcamp-alt",
            title="LLM Zoomcamp (alt form)",
            current_course=self.course,
        )
        self.assertNotIn("llm-zoomcamp-alt", self.suggested_slugs(limit=10))

    def test_excludes_already_registered_and_enrolled(self):
        CourseRegistration.objects.create(
            campaign=self.ml,
            email="student@example.com",
            name="Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.OTHER,
        )
        user = self.create_signed_user()
        Enrollment.objects.create(student=user, course=self.de.current_course)
        self.assertEqual(
            self.suggested_slugs(
                user=user, email="Student@Example.com", limit=10
            ),
            ["mlops-zoomcamp", "ai-dev-tools"],
        )

    def test_application_courses_are_link_only(self):
        Course.objects.filter(pk=self.ml.current_course_id).update(
            requires_registration_approval=True
        )
        by_slug = {
            s.campaign.slug: s for s in cross_sell.suggestions(self.campaign)
        }
        self.assertFalse(by_slug["ml-zoomcamp"].one_click)
        self.assertTrue(by_slug["de-zoomcamp"].one_click)
        self.assertIn(
            "src=xsell-link&from=llm-zoomcamp", by_slug["ml-zoomcamp"].url
        )


class SuccessPageTests(CrossSellBase):
    def test_success_page_shows_suggestions_and_records_impression(self):
        with patch("courses.cross_sell.record_event") as record:
            response = self.register()

        self.assertContains(response, "You might also like")
        self.assertContains(response, 'data-cross-sell-suggestion="ml-zoomcamp"')
        self.assertContains(response, "Register for selected")
        self.assertNotContains(
            response, 'data-cross-sell-suggestion="llm-zoomcamp"'
        )
        names = [call.args[0] for call in record.call_args_list]
        self.assertIn("cross_sell.impression", names)

    def test_application_only_suggestions_explain_apply(self):
        Course.objects.filter(
            registration_campaigns__in=[self.ml, self.de, self.mlops]
        ).update(requires_registration_approval=True)
        RegistrationCampaign.objects.filter(pk=self.next_cohort.pk).update(
            is_active=False
        )
        response = self.register()
        self.assertContains(response, "take applications")
        self.assertNotContains(response, "Register for selected")

    def test_form_page_without_registration_has_no_block(self):
        response = self.client.get(self.campaign_url())
        self.assertNotContains(response, "You might also like")

    def test_nothing_to_suggest_hides_block(self):
        RegistrationCampaign.objects.exclude(pk=self.campaign.pk).update(
            is_active=False
        )
        response = self.register()
        self.assertNotContains(response, "You might also like")


class OneClickRegistrationTests(CrossSellBase):
    def cross_sell_url(self):
        return reverse(
            "registration_cross_sell",
            kwargs={"campaign_slug": self.campaign.slug},
        )

    @patch("course_management.relay.registration.sync_registration_to_relay")
    def test_multi_select_registers_copies_without_reentry(self, sync):
        self.register()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.cross_sell_url(),
                {"campaigns": ["ml-zoomcamp", "de-zoomcamp"]},
            )

        self.assertRedirects(
            response, self.campaign_url(), fetch_redirect_response=False
        )
        source = self.source_registration()
        copies = CourseRegistration.objects.filter(referred_by=source)
        self.assertEqual(
            sorted(copies.values_list("campaign__slug", flat=True)),
            ["de-zoomcamp", "ml-zoomcamp"],
        )
        for copy in copies:
            self.assertEqual(copy.source, "xsell")
            self.assertEqual(copy.email_normalized, "student@example.com")
            self.assertEqual(copy.name, "Student One")
            self.assertEqual(copy.country, source.country)
            self.assertEqual(copy.course, copy.campaign.current_course)
            self.assertFalse(copy.email_confirmed)
            self.assertIsNone(copy.email_confirmation_token)
            self.assertFalse(copy.accepted_nebius_sharing)
        self.assertEqual(sync.call_count, 2)

        page = self.client.get(self.campaign_url())
        self.assertContains(page, "Also registered for:")
        self.assertNotContains(page, 'data-cross-sell-suggestion="ml-zoomcamp"')

    def test_single_button_registers_only_that_course(self):
        self.register()
        self.client.post(
            self.cross_sell_url(),
            {"campaign": "mlops-zoomcamp", "campaigns": ["ml-zoomcamp"]},
        )
        self.assertEqual(
            list(
                CourseRegistration.objects.filter(source="xsell").values_list(
                    "campaign__slug", flat=True
                )
            ),
            ["mlops-zoomcamp"],
        )

    def test_tampered_or_application_slugs_are_ignored(self):
        Course.objects.filter(pk=self.ml.current_course_id).update(
            requires_registration_approval=True
        )
        hidden = RegistrationCampaign.objects.create(
            slug="internal", title="Internal", exclude_from_suggestions=True
        )
        self.register()
        self.client.post(
            self.cross_sell_url(),
            {"campaigns": ["ml-zoomcamp", hidden.slug, "nope"]},
        )
        self.assertFalse(
            CourseRegistration.objects.filter(source="xsell").exists()
        )

    def test_without_source_registration_nothing_is_created(self):
        response = self.client.post(
            self.cross_sell_url(), {"campaigns": ["ml-zoomcamp"]}
        )
        self.assertRedirects(response, self.campaign_url())
        self.assertFalse(CourseRegistration.objects.exists())

    def test_double_submit_is_idempotent(self):
        self.register()
        self.client.post(self.cross_sell_url(), {"campaign": "ml-zoomcamp"})
        self.client.post(self.cross_sell_url(), {"campaign": "ml-zoomcamp"})
        self.assertEqual(
            CourseRegistration.objects.filter(campaign=self.ml).count(), 1
        )

    def test_logged_in_user_registers_with_account_identity(self):
        user = self.create_signed_user()
        self.client.force_login(user)
        self.client.post(self.campaign_url(), self.registration_payload())
        self.client.post(self.cross_sell_url(), {"campaign": "ml-zoomcamp"})
        copy = CourseRegistration.objects.get(campaign=self.ml)
        self.assertEqual(copy.user, user)
        self.assertEqual(copy.email_normalized, "signed@example.com")

    def test_copy_of_confirmed_source_is_confirmed(self):
        self.register()
        source = self.source_registration()
        source.email_confirmed = True
        source.save(update_fields=["email_confirmed"])
        self.client.post(self.cross_sell_url(), {"campaign": "ml-zoomcamp"})
        self.assertTrue(
            CourseRegistration.objects.get(campaign=self.ml).email_confirmed
        )


class ConfirmationCascadeTests(CrossSellBase):
    def setUp(self):
        super().setUp()
        self.register()
        self.source = self.source_registration()
        cross_sell.register_suggested(self.source, ["ml-zoomcamp"])
        self.copy = CourseRegistration.objects.get(campaign=self.ml)

    def test_confirming_source_confirms_copies(self):
        self.source.refresh_from_db()
        registration, outcome = confirm_registration_by_token(
            CourseRegistration, self.source.email_confirmation_token
        )
        self.assertEqual(outcome, "confirmed")
        self.copy.refresh_from_db()
        self.assertTrue(self.copy.email_confirmed)

    def test_copies_never_get_reminders_and_go_with_source(self):
        later = self.copy.created_at + datetime.timedelta(days=3)
        self.assertIsNone(reminder_action(self.copy, later))
        self.source.delete()
        self.assertFalse(
            CourseRegistration.objects.filter(pk=self.copy.pk).exists()
        )

    def test_fixing_source_email_drops_unconfirmed_copies(self):
        # Step past the resend cooldown.
        CourseRegistration.objects.filter(pk=self.source.pk).update(
            email_confirmation_sent_at=timezone.now()
            - datetime.timedelta(minutes=5)
        )
        self.client.post(
            reverse("registration_confirmation_fix_email"),
            {
                "token": self.source.confirmation_management_token,
                "email": "fixed@example.com",
            },
        )
        self.assertFalse(
            CourseRegistration.objects.filter(pk=self.copy.pk).exists()
        )


class LinkTrackingTests(CrossSellBase):
    def target_url(self, src):
        url = reverse(
            "registration_campaign", kwargs={"campaign_slug": "ml-zoomcamp"}
        )
        return f"{url}?src={src}&from=llm-zoomcamp"

    def test_email_link_click_is_attributed_to_registration(self):
        self.register()
        source = self.source_registration()
        with patch("courses.cross_sell.record_event") as record:
            self.client.get(self.target_url("xsell-email"))
            self.client.post(
                self.target_url("xsell-email"), self.registration_payload()
            )

        registration = CourseRegistration.objects.get(campaign=self.ml)
        self.assertEqual(registration.source, "xsell-email")
        self.assertEqual(registration.referred_by, source)
        names = [call.args[0] for call in record.call_args_list]
        self.assertIn("cross_sell.click", names)
        self.assertIn("cross_sell.registered", names)

    def test_unknown_src_is_not_tracked(self):
        self.client.get(self.target_url("spam"))
        self.client.post(
            self.target_url("spam"), self.registration_payload()
        )
        self.assertEqual(
            CourseRegistration.objects.get(campaign=self.ml).source, ""
        )


class ConfirmationEmailTests(CrossSellBase):
    def test_email_context_lists_suggestions_with_tracking_links(self):
        self.register()
        source = self.source_registration()
        issue_confirmation_token(source)
        urls = registration_confirmation_urls(
            self.campaign, self.course, token=source.email_confirmation_token
        )
        context = registration_confirmation_context(
            source, self.campaign, self.course, urls
        )

        titles = [item["title"] for item in context["suggested_courses"]]
        self.assertEqual(
            titles,
            ["ML Zoomcamp", "Data Engineering Zoomcamp", "MLOps Zoomcamp"],
        )
        first_url = context["suggested_courses"][0]["url"]
        self.assertIn("/register/ml-zoomcamp/", first_url)
        self.assertIn("src=xsell-email&from=llm-zoomcamp", first_url)
        self.assertIn("You might also like:", context["next_steps_text"])
        self.assertIn(first_url, context["next_steps_text"])

    def test_email_without_suggestions_keeps_next_steps_text(self):
        RegistrationCampaign.objects.exclude(pk=self.campaign.pk).update(
            is_active=False
        )
        self.register()
        source = self.source_registration()
        urls = registration_confirmation_urls(self.campaign, self.course)
        context = registration_confirmation_context(
            source, self.campaign, self.course, urls
        )
        self.assertEqual(context["suggested_courses"], [])
        self.assertNotIn("You might also like", context["next_steps_text"])
