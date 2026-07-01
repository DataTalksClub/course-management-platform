from dataclasses import dataclass

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Project,
    ProjectState,
    ProjectSubmission,
    Question,
    QuestionTypes,
    Submission,
    User,
)
from courses.tests.util import join_possible_answers


credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


@dataclass(frozen=True)
class HomeworkFixtureData:
    slug: str
    title: str
    description: str
    days_due: int
    state: str


@dataclass(frozen=True)
class ProjectFixtureData:
    title: str
    slug: str
    state: str
    submission_days: int


class CourseLeaderboardViewTestBase(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course-2"
        )

    def create_enrollment(self, user=None):
        return Enrollment.objects.create(
            student=user or self.user,
            course=self.course,
        )

    def create_homework(self, data: HomeworkFixtureData):
        due_date = timezone.now() + timezone.timedelta(days=data.days_due)
        return Homework.objects.create(
            slug=data.slug,
            course=self.course,
            title=data.title,
            description=data.description,
            due_date=due_date,
            state=data.state,
        )

    def create_homeworks(self):
        scored_homework_data = HomeworkFixtureData(
            slug="scored-homework",
            title="Scored Homework",
            description="This homework is already scored.",
            days_due=-1,
            state=HomeworkState.SCORED.value,
        )
        self.homework1 = self.create_homework(scored_homework_data)
        submitted_homework_data = HomeworkFixtureData(
            slug="submitted-homework",
            title="Submitted Homework",
            description="Homework with submitted answers.",
            days_due=7,
            state=HomeworkState.OPEN.value,
        )
        self.homework2 = self.create_homework(submitted_homework_data)
        unscored_homework_data = HomeworkFixtureData(
            slug="unscored-homework",
            title="Homework Without Submissions",
            description="Homework without any submissions yet.",
            days_due=14,
            state=HomeworkState.OPEN.value,
        )
        self.homework3 = self.create_homework(unscored_homework_data)
        self.homeworks = [
            self.homework1,
            self.homework2,
            self.homework3,
        ]

    def create_questions_for_homeworks(self):
        homeworks = self.homeworks
        for homework in homeworks:
            for index in range(1, 4):
                question_text = f"Question {index} of {homework.title}"
                possible_answers = join_possible_answers(
                    ["A", "B", "C", "D"]
                )
                Question.objects.create(
                    homework=homework,
                    text=question_text,
                    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                    possible_answers=possible_answers,
                    correct_answer="1",
                )

    def create_homework_submissions(self):
        self.submission1 = Submission.objects.create(
            homework=self.homework1,
            enrollment=self.enrollment,
            student=self.user,
            total_score=80,
        )
        self.submission2 = Submission.objects.create(
            homework=self.homework2,
            enrollment=self.enrollment,
            student=self.user,
            total_score=0,
        )

    def create_project(self, data: ProjectFixtureData):
        submission_due_date = timezone.now() + timezone.timedelta(
            days=data.submission_days
        )
        peer_review_due_date = timezone.now() + timezone.timedelta(days=14)
        return Project.objects.create(
            course=self.course,
            title=data.title,
            slug=data.slug,
            state=data.state,
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_projects(self):
        open_project_data = ProjectFixtureData(
            title="Open Project",
            slug="open-project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_days=7,
        )
        self.open_project = self.create_project(open_project_data)
        completed_project_data = ProjectFixtureData(
            title="Completed Project",
            slug="completed-project",
            state=ProjectState.COMPLETED.value,
            submission_days=-7,
        )
        self.completed_project = self.create_project(completed_project_data)

    def create_project_submissions(self):
        self.completed_submission = ProjectSubmission.objects.create(
            project=self.completed_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            project_score=85,
        )
        self.open_submission = ProjectSubmission.objects.create(
            project=self.open_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo2",
        )

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.create_homeworks()
        self.create_questions_for_homeworks()
        self.create_homework_submissions()
        self.create_projects()
        self.create_project_submissions()

    def create_leaderboard_enrollment(
        self, name, total_score, position_on_leaderboard=None
    ):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=student,
            display_name=name,
            total_score=total_score,
            position_on_leaderboard=position_on_leaderboard,
        )
        return enrollment

    def create_standard_leaderboard(self):
        self.create_leaderboard_enrollment("Alice", 100, 1)
        self.create_leaderboard_enrollment("Bob", 90, 2)
        self.create_leaderboard_enrollment("Charlie", 80, 3)

    def create_new_enrollment_leaderboard(self):
        leaderboard = {
            "e1": self.create_leaderboard_enrollment("e1", 0, None),
            "e2": self.create_leaderboard_enrollment("e2", 90, 1),
            "e3": self.create_leaderboard_enrollment("e3", 80, 2),
            "e4": self.create_leaderboard_enrollment("e4", 70, 3),
            "e5": self.create_leaderboard_enrollment("e5", 0, None),
        }
        return leaderboard

    def set_current_enrollment_leaderboard_position(self, score, position):
        self.enrollment.total_score = score
        self.enrollment.position_on_leaderboard = position
        self.enrollment.save()

    def leaderboard_response(self, *, login=False):
        if login:
            self.client.login(**credentials)
        url = self.leaderboard_url()
        return self.client.get(url)

    def leaderboard_url(self):
        return reverse("leaderboard", kwargs={"course_slug": self.course.slug})

    def leaderboard_score_breakdown_url(self, enrollment=None):
        target_enrollment = enrollment or self.enrollment
        kwargs = {
            "course_slug": self.course.slug,
            "enrollment_id": target_enrollment.id,
        }
        return reverse("leaderboard_score_breakdown", kwargs=kwargs)

    def leaderboard_complaint_url(self, enrollment):
        kwargs = {
            "course_slug": self.course.slug,
            "enrollment_id": enrollment.id,
        }
        return reverse("leaderboard_complaint", kwargs=kwargs)

    def assert_leaderboard_order(self, response, expected_order):
        enrollments = response.context["enrollments"]
        actual_order = []
        for enrollment in enrollments:
            display_name = enrollment["display_name"]
            actual_order.append(display_name)
        self.assertEqual(actual_order, expected_order)

    def assert_leaderboard_positions(self, response, expected_positions):
        enrollments = response.context["enrollments"]
        actual_positions = []
        for enrollment in enrollments:
            position = enrollment["position_on_leaderboard"]
            actual_positions.append(position)
        self.assertEqual(actual_positions, expected_positions)

    def assert_current_student_enrollment(self, response):
        current_enrollment = response.context.get("current_student_enrollment")
        current_enrollment_id = response.context.get(
            "current_student_enrollment_id"
        )
        self.assertIsNotNone(current_enrollment)
        self.assertEqual(current_enrollment.id, self.enrollment.id)
        self.assertEqual(current_enrollment.display_name, "TestUser")
        self.assertEqual(current_enrollment.total_score, 95)
        self.assertEqual(current_enrollment_id, self.enrollment.id)

    def assert_current_student_record_visible(self, response):
        self.assertContains(response, "Your Record")
        self.assertContains(response, "Your total score: 95")
        self.assertContains(response, "Position: 2")
        self.assertContains(response, "Display name: TestUser")
        self.assertContains(response, "Jump to my record")
        self.assertContains(response, f"record-{self.enrollment.id}")

    def assert_standard_leaderboard_visible(self, response):
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def set_homework_score_breakdown_fixture(self):
        self.submission1.questions_score = 7
        self.submission1.faq_score = 2
        self.submission1.learning_in_public_score = 1
        self.submission1.total_score = 10
        self.submission1.learning_in_public_links = [
            "https://example.com/homework-post",
        ]
        self.submission1.faq_contribution_url = (
            "https://github.com/DataTalksClub/faq/pull/266"
        )
        self.submission1.save()

    def set_project_score_breakdown_fixture(self):
        self.completed_submission.project_score = 20
        self.completed_submission.peer_review_score = 5
        self.completed_submission.project_learning_in_public_score = 3
        self.completed_submission.peer_review_learning_in_public_score = 2
        self.completed_submission.project_faq_score = 1
        self.completed_submission.total_score = 31
        self.completed_submission.learning_in_public_links = [
            "https://example.com/project-post",
        ]
        self.completed_submission.faq_contribution_url = (
            "https://github.com/DataTalksClub/faq/issues/266"
        )
        self.completed_submission.save()

    def assert_score_equations(self, response):
        response_body = response.content.decode()
        text_content = strip_tags(response_body)
        content_parts = text_content.split()
        content = " ".join(content_parts)
        self.assertIn(
            "Score: 10 = 7 (questions) + 2 (FAQ) + 1 "
            "(learning in public)",
            content,
        )
        self.assertIn(
            "Score: 31 = 20 (project) + 5 (peer review) + 3 "
            "(learning in public / project) + 2 "
            "(learning in public / peer review) + 1 (FAQ)",
            content,
        )

    def assert_score_breakdown_links(self, response):
        self.assertContains(response, "<details", count=2)
        self.assertContains(response, "<summary", count=2)
        self.assertContains(response, "<strong>FAQ URL:</strong>", count=2)
        self.assertContains(response, "View submission", count=2)
        self.assertContains(response, "https://example.com/homework-post")
        self.assertContains(response, "https://example.com/project-post")
        self.assertContains(
            response, "https://github.com/DataTalksClub/faq/pull/266"
        )
        self.assertContains(
            response, "https://github.com/DataTalksClub/faq/issues/266"
        )

    def assert_no_current_enrollment_context(self, response):
        current_enrollment = response.context.get("current_student_enrollment")
        current_enrollment_id = response.context.get(
            "current_student_enrollment_id"
        )
        self.assertIsNone(current_enrollment)
        self.assertIsNone(current_enrollment_id)

    def assert_no_current_record_visible(self, response):
        self.assertNotContains(response, "Your Record")
        self.assertNotContains(response, "Your total score")
        self.assertNotContains(response, "Display name")
        self.assertNotContains(response, "Jump to your record")

    def assert_leaderboard_names_visible(self, response):
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")
