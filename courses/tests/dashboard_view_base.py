from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from courses.models import Course, Enrollment


User = get_user_model()


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class DashboardViewTestBase(TestCase):
    @classmethod
    def create_dashboard_user(cls):
        cls.user = User.objects.create_user(**credentials)

    @classmethod
    def create_dashboard_course(cls):
        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Description",
            project_passing_score=70,
            first_homework_scored=True,
        )

    @classmethod
    def create_statistic_users(cls):
        user_data = []
        for i in range(5):
            user = User(
                username=f"user{i}@test.com",
                email=f"user{i}@test.com",
                password="12345",
            )
            user_data.append(user)

        cls.users = User.objects.bulk_create(user_data)

    @classmethod
    def create_statistic_enrollments(cls):
        enrollment_data = []
        for i, user in enumerate(cls.users):
            enrollment = Enrollment(
                student=user,
                course=cls.course,
                total_score=100 + i * 20,
            )
            enrollment_data.append(enrollment)

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollment_data
        )

    @classmethod
    def create_primary_enrollment(cls):
        cls.enrollment = Enrollment.objects.create(
            student=cls.user, course=cls.course, total_score=150
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.create_dashboard_user()
        cls.create_dashboard_course()
        cls.create_statistic_users()
        cls.create_statistic_enrollments()
        cls.create_primary_enrollment()

    def setUp(self):
        self.client = Client()
