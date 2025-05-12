from django.test import TestCase

from accounts.models import CustomUser
from courses.models import Course, Enrollment


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

    def test_certificate_name_sync_to_user(self):
        """Test that updating certificate name in enrollment updates it for the user but not other enrollments"""
        # Create two enrollments for the same user
        enrollment1 = Enrollment.objects.create(
            student=self.user,
            course=self.course1
        )
        enrollment2 = Enrollment.objects.create(
            student=self.user,
            course=self.course2
        )

        # Initially both enrollments and user should have no certificate name
        self.assertIsNone(enrollment1.certificate_name)
        self.assertIsNone(enrollment2.certificate_name)
        self.assertIsNone(self.user.certificate_name)

        # Update certificate name in first enrollment
        enrollment1.certificate_name = "John Doe"
        enrollment1.save()

        # Refresh objects from database
        self.user.refresh_from_db()
        enrollment1.refresh_from_db()
        enrollment2.refresh_from_db()

        # Check that only the user and the updated enrollment have the new certificate name
        self.assertEqual(enrollment1.certificate_name, "John Doe")
        self.assertIsNone(enrollment2.certificate_name)  # Other enrollment should not be affected
        self.assertEqual(self.user.certificate_name, "John Doe")  # User should be updated

    def test_certificate_name_sync_on_new_enrollment(self):
        """Test that new enrollment gets certificate name from user if set"""
        # Set certificate name on user
        self.user.certificate_name = "Jane Doe"
        self.user.save()

        # Create new enrollment
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course1
        )

        # Refresh enrollment from database
        enrollment.refresh_from_db()

        # Check that enrollment got the certificate name from user
        self.assertEqual(enrollment.certificate_name, "Jane Doe")

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

        # Check that enrollment's certificate name was not changed
        self.assertEqual(enrollment.certificate_name, "Original Name") 