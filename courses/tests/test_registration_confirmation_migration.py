from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ConfirmationMigrationTests(TransactionTestCase):
    def test_legacy_rows_are_grandfathered_without_changing_original_data(
        self,
    ):
        before = ("courses", "0050_application_notifications")
        after = (
            "courses",
            "0052_backfill_registration_email_confirmed",
        )
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
            course = Course.objects.create(
                slug="legacy-migration", title="Legacy"
            )
            campaign = Campaign.objects.create(
                slug="legacy-migration",
                title="Legacy",
                current_course=course,
            )
            registration = Registration.objects.create(
                pk=37875,
                campaign=campaign,
                course=course,
                email="Legacy@Example.com",
            )
            original = (
                Registration.objects.filter(pk=registration.pk)
                .values()
                .get()
            )
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            new_apps = executor.loader.project_state([after]).apps
            Registration = new_apps.get_model(
                "courses", "CourseRegistration"
            )
            row = Registration.objects.get(pk=37875)
            self.assertTrue(row.email_confirmed)
            self.assertIsNone(row.email_confirmation_token)
            self.assertEqual(row.email_confirmation_resend_count, 0)
            self.assertIsNotNone(row.email_confirmation_confirmed_at)
            for name, value in original.items():
                self.assertEqual(getattr(row, name), value, name)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
