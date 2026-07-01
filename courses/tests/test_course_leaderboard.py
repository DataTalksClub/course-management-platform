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
    LeaderboardComplaint,
    Project,
    ProjectState,
    ProjectSubmission,
    Question,
    QuestionTypes,
    Submission,
    User,
)

from .util import join_possible_answers


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


class CourseLeaderboardViewTests(TestCase):
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
        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        return self.client.get(url)

    def leaderboard_url(self):
        return reverse("leaderboard", kwargs={"course_slug": self.course.slug})

    def leaderboard_score_breakdown_url(self, enrollment=None):
        return reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": (enrollment or self.enrollment).id,
            },
        )

    def leaderboard_complaint_url(self, enrollment):
        return reverse(
            "leaderboard_complaint",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )

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
        self.assertIsNotNone(current_enrollment)
        self.assertEqual(current_enrollment.id, self.enrollment.id)
        self.assertEqual(current_enrollment.display_name, "TestUser")
        self.assertEqual(current_enrollment.total_score, 95)
        self.assertEqual(
            response.context.get("current_student_enrollment_id"),
            self.enrollment.id,
        )

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
        content = " ".join(strip_tags(response.content.decode()).split())
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

    def test_leaderboard_order(self):
        e1 = self.create_leaderboard_enrollment("e1", 100, 1)
        e2 = self.create_leaderboard_enrollment("e2", 90, 2)
        e3 = self.create_leaderboard_enrollment("e3", 80, 3)
        e4 = self.create_leaderboard_enrollment("e4", 70, 4)
        e5 = self.create_leaderboard_enrollment("e5", 60, 5)
        self.set_current_enrollment_leaderboard_position(50, 6)
        self.client.login(**credentials)

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        expected_order = [
            e1.display_name,
            e2.display_name,
            e3.display_name,
            e4.display_name,
            e5.display_name,
            self.enrollment.display_name,
        ]
        self.assert_leaderboard_order(response, expected_order)

    def test_new_enrollment_at_the_end_of_leaderboard(self):
        enrollments = self.create_new_enrollment_leaderboard()
        self.set_current_enrollment_leaderboard_position(50, 4)

        response = self.leaderboard_response(login=True)

        self.assertEqual(response.status_code, 200)
        expected_order = [
            enrollments["e2"].display_name,
            enrollments["e3"].display_name,
            enrollments["e4"].display_name,
            self.enrollment.display_name,
            enrollments["e1"].display_name,
            enrollments["e5"].display_name,
        ]
        self.assert_leaderboard_order(response, expected_order)
        self.assert_leaderboard_positions(response, [1, 2, 3, 4, None, None])

    def test_not_enrolled_yet_but_leaderboard_displays(self):
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)
        self.create_leaderboard_enrollment("e3", 80, 3)
        self.create_leaderboard_enrollment("e4", 70, 4)
        self.create_leaderboard_enrollment("e5", 60, 5)
        self.enrollment.delete()
        self.client.login(**credentials)

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        current_enrollment = response.context["current_student_enrollment"]
        self.assertIsNone(current_enrollment)

    def test_leaderboard_links_to_score_breakdown_without_flag_button(self):
        self.create_leaderboard_enrollment("e1", 100, 1)

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "e1")
        self.assertNotContains(response, "Flag this record")

    def test_score_breakdown_has_flag_button(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        response = self.client.get(self.leaderboard_score_breakdown_url(target))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flag this record")

    def test_score_breakdown_prompts_owner_to_show_public_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(self.leaderboard_score_breakdown_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Show public profile")
        self.assertContains(
            response,
            f'href="{reverse("enrollment", args=[self.course.slug])}"',
        )

    def test_score_breakdown_does_not_prompt_for_other_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.force_login(self.user)

        response = self.client.get(self.leaderboard_score_breakdown_url(target))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_does_not_prompt_when_profile_public(self):
        self.enrollment.display_public_profile = True
        self.enrollment.save()
        self.client.force_login(self.user)

        response = self.client.get(self.leaderboard_score_breakdown_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_shows_score_equations(self):
        self.set_homework_score_breakdown_fixture()
        self.set_project_score_breakdown_fixture()

        response = self.client.get(self.leaderboard_score_breakdown_url())

        self.assert_score_equations(response)
        self.assert_score_breakdown_links(response)

    def test_authenticated_user_can_report_leaderboard_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.login(**credentials)
        complaint_data = {
            "issue_type": LeaderboardComplaint.IssueType.HOMEWORK,
            "description": "Homework score looks incorrect.",
        }

        response = self.client.post(
            self.leaderboard_complaint_url(target),
            complaint_data,
        )

        self.assertRedirects(
            response,
            self.leaderboard_score_breakdown_url(target),
        )
        complaint = LeaderboardComplaint.objects.get(enrollment=target)
        self.assertEqual(complaint.reporter, self.user)
        self.assertEqual(
            complaint.issue_type,
            LeaderboardComplaint.IssueType.HOMEWORK,
        )

    def test_anonymous_user_is_redirected_when_reporting(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        response = self.client.get(self.leaderboard_complaint_url(target))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_leaderboard_view_does_not_auto_enroll(self):
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)
        self.enrollment.delete()
        self.client.login(**credentials)

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        ).count()
        self.assertEqual(enrollment_count, 0)
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)

    def test_leaderboard_unauthenticated_user(self):
        self.create_standard_leaderboard()
        self.client.logout()

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        self.assert_no_current_enrollment_context(response)
        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 4)
        self.assert_no_current_record_visible(response)
        self.assert_leaderboard_names_visible(response)

    def test_leaderboard_authenticated_without_enrollment(self):
        self.create_standard_leaderboard()
        self.enrollment.delete()
        self.client.login(**credentials)

        response = self.client.get(self.leaderboard_url())

        self.assertEqual(response.status_code, 200)
        self.assert_no_current_enrollment_context(response)
        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 3)
        self.assert_no_current_record_visible(response)
        self.assert_leaderboard_names_visible(response)

    def test_leaderboard_authenticated_with_enrollment(self):
        self.create_standard_leaderboard()
        self.enrollment.display_name = "TestUser"
        self.enrollment.total_score = 95
        self.enrollment.position_on_leaderboard = 2
        self.enrollment.save()

        response = self.leaderboard_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assert_current_student_enrollment(response)
        self.assertEqual(len(response.context["enrollments"]), 4)
        self.assert_current_student_record_visible(response)
        self.assert_standard_leaderboard_visible(response)
        self.assertContains(response, "TestUser")
