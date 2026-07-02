from dataclasses import dataclass

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
    HomeworkState,
    Project,
    ProjectState,
    ProjectSubmission,
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


@dataclass(frozen=True)
class ScoredHomeworkExpectation:
    homework: Homework
    submitted: bool
    score: int | None
    with_submitted_at: bool = False


@dataclass(frozen=True)
class OpenHomeworkExpectation:
    homework: Homework
    submitted: bool
    score: int | None
    days_until_due: int


class CourseDetailViewTestBase(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course-2"
        )

    def create_enrollment(self, user=None):
        student = user or self.user
        return Enrollment.objects.create(
            student=student,
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
        possible_answers = join_possible_answers(["A", "B", "C", "D"])
        for homework in self.homeworks:
            for index in range(1, 4):
                Question.objects.create(
                    homework=homework,
                    text=f"Question {index} of {homework.title}",
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
        ProjectSubmission.objects.create(
            project=self.completed_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            project_score=85,
        )
        ProjectSubmission.objects.create(
            project=self.open_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo2",
        )

    def course_url(self):
        return reverse("course", kwargs={"course_slug": self.course.slug})

    def get_course_response(self, login=False):
        if login:
            self.client.login(**credentials)
        course_url = self.course_url()
        return self.client.get(course_url)

    def homeworks_by_slug(self, response):
        homeworks_by_slug = {}
        homeworks = response.context["homeworks"]
        for homework in homeworks:
            homeworks_by_slug[homework.slug] = homework
        return homeworks_by_slug

    def assert_course_context(self, context, authenticated):
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertEqual(context["is_authenticated"], authenticated)

    def assert_scored_homework(self, data: ScoredHomeworkExpectation):
        self.assertEqual(data.homework.submitted, data.submitted)
        is_scored = data.homework.is_scored()
        self.assertEqual(is_scored, True)
        self.assertEqual(data.homework.state, HomeworkState.SCORED.value)
        self.assertEqual(data.homework.score, data.score)
        self.assertEqual(data.homework.days_until_due, 0)
        if not data.with_submitted_at:
            has_submitted_at = hasattr(data.homework, "submitted_at")
            self.assertFalse(has_submitted_at)

    def assert_open_homework(self, data: OpenHomeworkExpectation):
        self.assertEqual(data.homework.submitted, data.submitted)
        self.assertEqual(data.homework.state, HomeworkState.OPEN.value)
        is_scored = data.homework.is_scored()
        self.assertEqual(is_scored, False)
        self.assertEqual(data.homework.score, data.score)
        self.assertEqual(data.homework.days_until_due, data.days_until_due)

    def assert_unsubmitted_open_homework(self, homework):
        self.assertFalse(homework.submitted)
        has_submitted_at = hasattr(homework, "submitted_at")
        self.assertFalse(has_submitted_at)
        is_scored = homework.is_scored()
        self.assertEqual(is_scored, False)
        self.assertEqual(homework.score, None)
        self.assertEqual(homework.days_until_due, 14)
        self.assertEqual(homework.submissions, [])


    def assert_enrollment_profile_links(self, response):
        self.assertContains(response, "account timezone")
        account_settings_url = (
            f'{reverse("account_settings")}#display-preferences-section'
        )
        self.assertContains(
            response,
            account_settings_url,
        )
        self.assertContains(response, "Edit course profile")
        enrollment_url = reverse(
            "enrollment",
            kwargs={"course_slug": self.course.slug},
        )
        self.assertContains(
            response,
            enrollment_url,
        )

    def assert_no_enrollment_profile_links(self, response):
        self.assertContains(response, "Total score")
        self.assertContains(response, "N/A")
        self.assertNotContains(response, "None")
        self.assertNotContains(response, "Edit course profile")
        enrollment_url = reverse(
            "enrollment",
            kwargs={"course_slug": self.course.slug},
        )
        self.assertNotContains(
            response,
            enrollment_url,
        )

    def assert_enrolled_course_context(self, response, total_score):
        self.assertEqual(response.context["total_score"], total_score)
        self.assertTrue(response.context["has_enrollment"])
        self.assert_enrollment_profile_links(response)


    def assert_authenticated_homework_summary(self, response):
        homeworks = self.homeworks_by_slug(response)
        scored_expectation = ScoredHomeworkExpectation(
            homework=homeworks["scored-homework"],
            submitted=True,
            score=80,
        )
        self.assert_scored_homework(scored_expectation)
        submitted_homework = homeworks["submitted-homework"]
        open_expectation = OpenHomeworkExpectation(
            homework=submitted_homework,
            submitted=True,
            score=None,
            days_until_due=7,
        )
        self.assert_open_homework(open_expectation)
        self.assertEqual(
            submitted_homework.submitted_at,
            self.submission2.submitted_at,
        )
        self.assert_unsubmitted_open_homework(
            homeworks["unscored-homework"]
        )

    def assert_not_enrolled_homework_summary(self, response):
        homeworks = self.homeworks_by_slug(response)
        scored_expectation = ScoredHomeworkExpectation(
            homework=homeworks["scored-homework"],
            submitted=False,
            score=None,
        )
        self.assert_scored_homework(scored_expectation)

        submitted_homework = homeworks["submitted-homework"]
        open_expectation = OpenHomeworkExpectation(
            homework=submitted_homework,
            submitted=False,
            score=None,
            days_until_due=7,
        )
        self.assert_open_homework(open_expectation)

        unscored_homework = homeworks["unscored-homework"]
        self.assert_unsubmitted_open_homework(unscored_homework)


    def create_due_homework(self, slug, title, days_due):
        homework_data = HomeworkFixtureData(
            slug=slug,
            title=title,
            description=f"{title} description",
            days_due=days_due,
            state=HomeworkState.OPEN.value,
        )
        homework = self.create_homework(homework_data)
        possible_answers = join_possible_answers(["A", "B", "C"])
        Question.objects.create(
            homework=homework,
            text=f"Question for {homework.title}",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=possible_answers,
            correct_answer="1",
        )
        return homework

    def create_sorted_homework_fixture(self):
        self.create_due_homework("homework-late", "Late Homework", 30)
        self.create_due_homework("homework-early", "Early Homework", 5)
        self.create_due_homework("homework-middle", "Middle Homework", 15)

    def assert_homeworks_in_due_order(self, response):
        homeworks = response.context["homeworks"]
        self.assertEqual(len(homeworks), 6)
        homework_slugs = []
        for homework in homeworks:
            homework_slugs.append(homework.slug)
        early_pos = homework_slugs.index("homework-early")
        middle_pos = homework_slugs.index("homework-middle")
        late_pos = homework_slugs.index("homework-late")
        self.assertLess(early_pos, middle_pos)
        self.assertLess(middle_pos, late_pos)


    def create_peer_review_project(self):
        submission_due_date = timezone.now() - timezone.timedelta(days=1)
        peer_review_due_date = timezone.now() + timezone.timedelta(days=7)
        return Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_project_submitter(self, project):
        user = User.objects.create_user(
            username="submitted@test.com",
            email="submitted@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/pr-repo",
        )
        return user

    def assert_course_page_contains_deadline(self, deadline):
        course_url = self.course_url()
        response = self.client.get(course_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        formatted_deadline = deadline.strftime("%Y-%m-%d")
        self.assertIn(formatted_deadline, content)

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
