from dataclasses import dataclass

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
    User,
)

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


@dataclass(frozen=True)
class ProjectFixtureData:
    title: str
    slug: str
    state: str
    submission_days: int


class CourseProjectSubmissionsViewTests(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course-2"
        )

    def create_enrollment(self, user=None, display_name=""):
        return Enrollment.objects.create(
            student=user or self.user,
            course=self.course,
            display_name=display_name,
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
        self.create_projects()
        self.create_project_submissions()

    def submissions_url(self):
        return reverse(
            "list_all_project_submissions", args=[self.course.slug]
        )

    def get_submissions_response(self, login=False):
        if login:
            self.client.login(**credentials)
        submissions_url = self.submissions_url()
        return self.client.get(submissions_url)

    def create_paginated_submissions(self):
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index}",
                email=f"student-{index}@example.com",
                password="12345",
            )
            display_name = f"Student {index}"
            enrollment = self.create_enrollment(user, display_name)
            ProjectSubmission.objects.create(
                project=self.open_project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/test/repo-{index}",
            )

    def user_submissions_by_project(self, submissions):
        user_submissions = {}
        for submission in submissions:
            if submission.enrollment.student == self.user:
                user_submissions[submission.project_id] = submission
        return user_submissions

    def assert_submission_order(self, submissions):
        self.assertEqual(len(submissions), 2)
        self.assertEqual(submissions[0].project, self.completed_project)
        self.assertEqual(submissions[0].display_score, 85)
        self.assertEqual(submissions[1].project, self.open_project)
        self.assertEqual(submissions[1].display_score, -1)

    def assert_leaderboard_link(self, response):
        leaderboard_url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": self.enrollment.id,
            },
        )
        self.assertContains(response, leaderboard_url)

    def assert_project_links(self, response):
        self.assertContains(response, "Project lists")
        completed_project_url = reverse(
            "project_list",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.completed_project.slug,
            },
        )
        self.assertContains(response, completed_project_url)
        open_project_url = reverse(
            "project_list",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.open_project.slug,
            },
        )
        self.assertContains(response, open_project_url)

    def assert_evaluated_submission(self, submission):
        self.assertEqual(submission.project, self.completed_project)
        self.assertEqual(submission.display_score, 85)
        self.assertEqual(submission.enrollment.student, self.user)

    def assert_open_submission(self, submission):
        self.assertEqual(submission.project, self.open_project)
        self.assertEqual(submission.display_score, -1)
        self.assertEqual(submission.enrollment.student, self.user)

    def test_list_all_submissions_view(self):
        response = self.get_submissions_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list_all.html")

        submissions = response.context["submissions"]
        self.assert_submission_order(submissions)

    def test_list_all_submissions_links_student_to_repository(self):
        response = self.get_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assert_leaderboard_link(response)
        self.assertContains(response, self.completed_submission.github_link)
        self.assertContains(response, 'aria-label="Open repository"')

    def test_list_all_submissions_links_to_each_project_list(self):
        response = self.get_submissions_response()

        self.assertEqual(response.status_code, 200)
        self.assert_project_links(response)

    def test_list_all_submissions_view_is_paginated(self):
        self.create_paginated_submissions()

        response = self.get_submissions_response()

        self.assertEqual(response.status_code, 200)
        submissions_page = response.context["submissions_page"]
        self.assertEqual(submissions_page.paginator.count, 32)
        self.assertEqual(len(response.context["submissions"]), 25)
        has_next_page = submissions_page.has_next()
        self.assertTrue(has_next_page)

    def test_list_all_submissions_view_unauthorized(self):
        response = self.get_submissions_response()
        self.assertEqual(response.status_code, 200)

    def test_submissions_display_format(self):
        response = self.get_submissions_response(login=True)
        self.assertEqual(response.status_code, 200)

        submissions = response.context["submissions"]
        user_submissions = self.user_submissions_by_project(submissions)

        self.assertEqual(len(user_submissions), 2)

        evaluated_submission = user_submissions[self.completed_project.id]
        self.assert_evaluated_submission(evaluated_submission)

        open_submission = user_submissions[self.open_project.id]
        self.assert_open_submission(open_submission)
