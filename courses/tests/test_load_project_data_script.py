from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from courses.models import Course, Enrollment
from scripts.load_project_data import (
    ImportMaps,
    create_enrollments,
    create_users,
)


User = get_user_model()


def quiet_tqdm(items, **_kwargs):
    return items


class LoadProjectDataScriptTest(TestCase):
    def run_quiet_import_step(self, import_step, *args):
        with patch("scripts.load_project_data.tqdm", quiet_tqdm):
            with redirect_stdout(StringIO()):
                import_step(*args)

    def test_create_users_maps_existing_and_created_users(self):
        existing = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
        )
        maps = ImportMaps()
        records = [
            {"id": 10, "username": existing.username, "email": existing.email},
            {
                "id": 11,
                "username": "new@example.com",
                "email": "new@example.com",
                "certificate_name": "New User",
                "dark_mode": True,
            },
        ]

        self.run_quiet_import_step(create_users, records, maps)

        created = User.objects.get(username="new@example.com")
        self.assertEqual(maps.user_id_map[10], existing.id)
        self.assertEqual(maps.user_id_map[11], created.id)
        self.assertEqual(created.certificate_name, "New User")
        self.assertTrue(created.dark_mode)

    def create_enrollment_import_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
        )

    def create_enrollment_import_users(self):
        existing_user = User.objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
        )
        new_user = User.objects.create_user(
            username="new@example.com",
            email="new@example.com",
        )
        return existing_user, new_user

    def enrollment_import_records(self):
        return [
            {"id": 20, "student_id": 10, "enrollment_date": None},
            {
                "id": 21,
                "student_id": 11,
                "enrollment_date": None,
                "display_name": "New Student",
            },
        ]

    def enrollment_import_maps(self, existing_user, new_user):
        return ImportMaps(
            user_id_map={10: existing_user.id, 11: new_user.id}
        )

    def test_create_enrollments_maps_existing_and_created_enrollments(self):
        course = self.create_enrollment_import_course()
        existing_user, new_user = self.create_enrollment_import_users()
        existing_enrollment = Enrollment.objects.create(
            student=existing_user,
            course=course,
        )
        maps = self.enrollment_import_maps(existing_user, new_user)
        records = self.enrollment_import_records()

        self.run_quiet_import_step(create_enrollments, records, course, maps)

        created = Enrollment.objects.get(student=new_user, course=course)
        self.assertEqual(maps.enrollment_id_map[20], existing_enrollment.id)
        self.assertEqual(maps.enrollment_id_map[21], created.id)
        self.assertEqual(created.display_name, "New Student")
