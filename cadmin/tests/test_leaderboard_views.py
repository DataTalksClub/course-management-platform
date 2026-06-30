from dataclasses import dataclass

from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course, Enrollment, LeaderboardComplaint, User


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)

admin_credentials = dict(
    username="admin@test.com",
    password="admin123",
)


@dataclass(frozen=True)
class LeaderboardEnrollmentData:
    username: str
    display_name: str
    total_score: int
    position: int


class LeaderboardCadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_leaderboard_enrollment(self, data):
        return Enrollment.objects.create(
            student=User.objects.create_user(username=data.username),
            course=self.course,
            display_name=data.display_name,
            total_score=data.total_score,
            position_on_leaderboard=data.position,
        )

    def create_complaint_reporter(self):
        return User.objects.create_user(
            username="reporter@test.com",
            email="reporter@test.com",
            password="12345",
        )

    def create_complaint_sorting_target(self, reporter):
        first_enrollment = LeaderboardEnrollmentData(
            username="first@test.com",
            display_name="First Student",
            total_score=10,
            position=2,
        )
        first = self.create_leaderboard_enrollment(first_enrollment)
        second_enrollment = LeaderboardEnrollmentData(
            username="second@test.com",
            display_name="Second Student",
            total_score=20,
            position=1,
        )
        second = self.create_leaderboard_enrollment(second_enrollment)
        LeaderboardComplaint.objects.create(
            enrollment=first,
            reporter=reporter,
            issue_type=LeaderboardComplaint.IssueType.HOMEWORK,
            description="Incorrect homework.",
        )
        LeaderboardComplaint.objects.create(
            enrollment=second,
            reporter=reporter,
            issue_type=LeaderboardComplaint.IssueType.PROJECT,
            description="Incorrect project.",
        )
        LeaderboardComplaint.objects.create(
            enrollment=second,
            reporter=reporter,
            issue_type=LeaderboardComplaint.IssueType.LEARNING_IN_PUBLIC,
            description="Incorrect learning links.",
        )
        return second

    def assert_most_complained_enrollment_first(self, response, enrollment):
        rows = response.context["enrollment_rows"]
        self.assertEqual(rows[0]["enrollment"], enrollment)
        self.assertEqual(rows[0]["enrollment"].open_complaints, 2)

    def test_leaderboard_complaints_sorted_by_open_count(self):
        self.client.login(**admin_credentials)
        reporter = self.create_complaint_reporter()
        second = self.create_complaint_sorting_target(reporter)
        url = reverse(
            "cadmin_leaderboard_complaints",
            kwargs={"course_slug": self.course.slug},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_most_complained_enrollment_first(response, second)
        self.assertContains(response, "Second Student")

    def test_staff_can_resolve_leaderboard_complaint(self):
        self.client.login(**admin_credentials)
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Reported Student",
            total_score=10,
        )
        complaint = LeaderboardComplaint.objects.create(
            enrollment=enrollment,
            reporter=self.user,
            issue_type=LeaderboardComplaint.IssueType.HOMEWORK,
            description="Incorrect homework.",
        )
        resolve_url = reverse(
            "cadmin_leaderboard_complaint_resolve",
            kwargs={
                "course_slug": self.course.slug,
                "complaint_id": complaint.id,
            },
        )
        complaints_url = reverse(
            "cadmin_leaderboard_complaints",
            kwargs={"course_slug": self.course.slug},
        )

        response = self.client.post(resolve_url)

        self.assertRedirects(response, complaints_url)
        complaint.refresh_from_db()
        self.assertTrue(complaint.resolved)
        self.assertEqual(complaint.resolved_by, self.admin_user)
