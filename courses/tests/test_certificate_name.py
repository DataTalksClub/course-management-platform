from django.test import TestCase

from accounts.models import CustomUser
from courses.models import Course, Enrollment
from courses.views.forms import EnrollmentForm


class CertificateNameTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="12345"
        )
        self.course1 = Course.objects.create(
            title="Test Course 1",
            slug="test-course-1"
        )
        self.course2 = Course.objects.create(
            title="Test Course 2",
            slug="test-course-2"
        )

    def test_enrollment_certificate_name_does_not_update_user(self):
        """Enrollment certificate_name is legacy storage, not the source of truth."""
        enrollment1 = Enrollment.objects.create(
            student=self.user,
            course=self.course1
        )
        enrollment2 = Enrollment.objects.create(
            student=self.user,
            course=self.course2
        )

        self.assertIsNone(enrollment1.certificate_name)
        self.assertIsNone(enrollment2.certificate_name)
        self.assertIsNone(self.user.certificate_name)

        enrollment1.certificate_name = "John Doe"
        enrollment1.save()

        self.user.refresh_from_db()
        enrollment1.refresh_from_db()
        enrollment2.refresh_from_db()

        self.assertEqual(enrollment1.certificate_name, "John Doe")
        self.assertIsNone(enrollment2.certificate_name)
        self.assertIsNone(self.user.certificate_name)

    def test_new_enrollment_does_not_copy_user_certificate_name(self):
        """Certificate name is read from the user directly when needed."""
        self.user.certificate_name = "Jane Doe"
        self.user.save()

        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course1
        )

        enrollment.refresh_from_db()

        self.assertIsNone(enrollment.certificate_name)

    def test_certificate_name_not_overwritten(self):
        """Test that existing certificate name in enrollment is not overwritten by user's name"""
        # Create enrollment with certificate name
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course1,
            certificate_name="Original Name"
        )

        # Set different certificate name on user
        self.user.certificate_name = "Different Name"
        self.user.save()

        # Refresh enrollment from database
        enrollment.refresh_from_db()

        self.assertEqual(enrollment.certificate_name, "Original Name")

    def test_enrollment_form_certificate_name_saves_to_user(self):
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course1,
            display_name="Leaderboard Name",
        )

        form = EnrollmentForm(
            data={
                "display_name": "Leaderboard Name",
                "certificate_name": "Certificate Name",
                "display_public_profile": "on",
            },
            instance=enrollment,
            user=self.user,
        )

        self.assertTrue(form.is_valid())
        form.save()

        self.user.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(self.user.certificate_name, "Certificate Name")
        self.assertIsNone(enrollment.certificate_name)
