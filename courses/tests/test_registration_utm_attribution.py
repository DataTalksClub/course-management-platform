from django.urls import reverse

from accounts.models import CustomUser
from api.views.registration_campaign_serializers import registration_to_dict
from cadmin.views.campaign_analytics import analytics_context
from courses.models import CourseRegistration
from courses.tests.registration_campaign_base import (
    RegistrationCampaignBase,
)

UTM_QUERY = (
    "?utm_source=mlops-community&utm_medium=newsletter"
    "&utm_campaign=genmedia-promo&utm_content=top&utm_term=agents"
)


class RegistrationUtmAttributionTests(RegistrationCampaignBase):
    def register(self, email="Student@Example.com"):
        return self.client.post(
            self.campaign_url(), self.registration_payload(email=email)
        )

    def test_utm_survives_form_submit_and_is_stored(self):
        self.client.get(
            self.campaign_url() + UTM_QUERY,
            HTTP_REFERER="https://mlops.community/newsletter",
        )
        self.register()
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.utm_source, "mlops-community")
        self.assertEqual(registration.utm_medium, "newsletter")
        self.assertEqual(registration.utm_campaign, "genmedia-promo")
        self.assertEqual(registration.utm_content, "top")
        self.assertEqual(registration.utm_term, "agents")
        self.assertEqual(
            registration.landing_referrer,
            "https://mlops.community/newsletter",
        )

    def test_untagged_registration_has_empty_attribution(self):
        self.client.get(self.campaign_url())
        self.register()
        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.utm_source, "")
        self.assertEqual(registration.landing_referrer, "")

    def test_later_untagged_visit_keeps_utm(self):
        self.client.get(self.campaign_url() + UTM_QUERY)
        self.client.get(self.campaign_url())
        self.register()
        self.assertEqual(
            CourseRegistration.objects.get().utm_source, "mlops-community"
        )

    def test_values_are_truncated(self):
        self.client.get(self.campaign_url() + "?utm_source=" + "x" * 500)
        self.register()
        self.assertEqual(len(CourseRegistration.objects.get().utm_source), 100)

    def test_same_site_referrer_is_not_stored(self):
        self.client.get(
            self.campaign_url() + "?utm_source=a",
            HTTP_REFERER="http://testserver/courses/",
        )
        self.register()
        self.assertEqual(CourseRegistration.objects.get().landing_referrer, "")

    def test_api_dict_includes_utm(self):
        self.client.get(self.campaign_url() + UTM_QUERY)
        self.register()
        data = registration_to_dict(CourseRegistration.objects.get())
        self.assertEqual(data["utm_source"], "mlops-community")
        self.assertEqual(data["utm_campaign"], "genmedia-promo")

    def test_analytics_counts_by_utm_source(self):
        self.client.get(self.campaign_url() + UTM_QUERY)
        self.register("a@example.com")
        self.client.logout()
        self.client.cookies.clear()
        self.register("b@example.com")
        context = analytics_context(self.campaign, None, None)
        rows = dict(context["breakdowns"])["UTM source"]
        counts = {row["label"]: row["count"] for row in rows}
        self.assertEqual(counts, {"mlops-community": 1, "No UTM source": 1})

    def test_staff_csv_export_has_utm_columns(self):
        self.client.get(self.campaign_url() + UTM_QUERY)
        self.register()
        CustomUser.objects.create_user(
            username="staff", email="staff@example.com",
            password="pw", is_staff=True, is_superuser=True,
        )
        self.client.login(username="staff@example.com", password="pw")
        response = self.client.get(
            reverse(
                "cadmin_campaign_registrations_export",
                kwargs={"campaign_slug": self.campaign.slug},
            )
        )
        text = response.content.decode()
        header, row = text.splitlines()[:2]
        self.assertIn("utm_source", header)
        self.assertIn("mlops-community", row)
