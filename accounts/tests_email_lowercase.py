import importlib

from django.apps import apps as global_apps
from django.test import TestCase

from accounts.models import CustomUser

lowercase_existing_emails = importlib.import_module(
    "accounts.migrations.0011_lowercase_existing_emails"
).lowercase_existing_emails


class CustomUserEmailLowercaseTestCase(TestCase):
    def test_save_lowercases_email_on_create(self):
        user = CustomUser.objects.create(
            username="mixedcase",
            email="Mixed.Case@Example.com",
            password="password",
        )

        self.assertEqual(user.email, "mixed.case@example.com")

    def test_save_lowercases_email_on_update(self):
        user = CustomUser.objects.create(
            username="updateduser",
            email="lower@example.com",
            password="password",
        )

        user.email = "Updated.Case@Example.com"
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.email, "updated.case@example.com")


class LowercaseExistingEmailsMigrationTestCase(TestCase):
    def create_user_with_raw_email(self, username, email):
        # bulk_update bypasses CustomUser.save(), so this stores the email
        # exactly as given, letting the test set up pre-migration state.
        user = CustomUser.objects.create(
            username=username,
            email="placeholder@example.com",
            password="password",
        )
        CustomUser.objects.filter(id=user.id).update(email=email)
        user.refresh_from_db()
        return user

    def run_migration(self):
        lowercase_existing_emails(global_apps, None)

    def test_lowercases_mixed_case_email(self):
        user = self.create_user_with_raw_email(
            "mixeduser", "Mixed.Case@Example.com"
        )

        self.run_migration()

        user.refresh_from_db()
        self.assertEqual(user.email, "mixed.case@example.com")

    def test_leaves_already_lowercase_email_untouched(self):
        user = self.create_user_with_raw_email(
            "lowerduser", "already.lower@example.com"
        )

        self.run_migration()

        user.refresh_from_db()
        self.assertEqual(user.email, "already.lower@example.com")

    def test_skips_case_collisions_without_merging(self):
        first = self.create_user_with_raw_email(
            "collideone", "Collide@Example.com"
        )
        second = self.create_user_with_raw_email(
            "collidetwo", "collide@example.com"
        )

        self.run_migration()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.email, "Collide@Example.com")
        self.assertEqual(second.email, "collide@example.com")
