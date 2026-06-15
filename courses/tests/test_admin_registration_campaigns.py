from django.contrib import admin
from django.test import TestCase

from courses.models import CourseRegistration, RegistrationCampaign


class RegistrationCampaignAdminTests(TestCase):
    def test_registration_models_are_registered_in_django_admin(self):
        self.assertIn(RegistrationCampaign, admin.site._registry)
        self.assertIn(CourseRegistration, admin.site._registry)

    def test_registration_campaign_admin_prepopulates_slug(self):
        model_admin = admin.site._registry[RegistrationCampaign]

        self.assertEqual(model_admin.prepopulated_fields, {"slug": ("title",)})
