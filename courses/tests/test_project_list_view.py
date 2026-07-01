from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    PeerReview,
    Project,
    ProjectState,
    ProjectSubmission,
    User,
)

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectListViewTests(TestCase):
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_enrollment(self, user, display_name=""):
        return Enrollment.objects.create(
            student=user,
            course=self.course,
            display_name=display_name,
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
            state=ProjectState.PEER_REVIEWING.value,
        )

    def create_project_submission(self, user, enrollment, github_link):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link=github_link,
            commit_id="1234567",
        )

    def create_peer_review(self):
        return PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            optional=False,
        )

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment(self.user)
        self.project = self.create_project()
        self.submission = self.create_project_submission(
            self.user,
            self.enrollment,
            "https://github.com/user/project",
        )
        self.other_user = User.objects.create_user(
            username="student",
            email="email@email.com",
            password="12345",
        )
        self.other_enrollment = self.create_enrollment(self.other_user)
        self.other_submission = self.create_project_submission(
            self.other_user,
            self.other_enrollment,
            "https://github.com/other_student/project",
        )
        self.peer_review = self.create_peer_review()

    def project_list_url(self):
        return reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

    def get_project_list_response(self, login=False):
        if login:
            self.client.login(**credentials)
        project_list_url = self.project_list_url()
        return self.client.get(project_list_url)

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
                project=self.project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/student-{index}/project",
                commit_id="1234567",
            )

    def assert_add_to_evaluation_visible(self, response):
        self.assertContains(
            response,
            'aria-label="Add to evaluation"',
            status_code=200,
        )

    def assert_project_list_response(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list.html")

    def test_list_view_authenticated_no_submission(self):
        self.submission.delete()

        response = self.get_project_list_response(login=True)

        self.assert_project_list_response(response)
        self.assertFalse(response.context["has_submission"])
        self.assert_add_to_evaluation_visible(response)
        self.assertNotContains(response, "Other submissions")

    def test_list_view_authenticated_with_submission(self):
        self.peer_review.delete()

        response = self.get_project_list_response(login=True)

        self.assert_project_list_response(response)
        self.assertTrue(response.context["has_submission"])
        self.assert_add_to_evaluation_visible(response)

    def test_project_list_links_student_to_repository(self):
        response = self.get_project_list_response()

        self.assertEqual(response.status_code, 200)
        leaderboard_url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": self.enrollment.id,
            },
        )
        self.assertContains(response, leaderboard_url)
        self.assertContains(response, self.submission.github_link)
        self.assertContains(response, 'aria-label="Open repository"')
        submissions_url = reverse(
            "list_all_project_submissions", args=[self.course.slug]
        )
        self.assertContains(response, submissions_url)

    def test_project_list_view_is_paginated(self):
        self.create_paginated_submissions()

        response = self.get_project_list_response()

        self.assertEqual(response.status_code, 200)
        submissions_page = response.context["submissions_page"]
        self.assertEqual(submissions_page.paginator.count, 32)
        self.assertEqual(len(response.context["submissions"]), 25)
        has_next_page = submissions_page.has_next()
        self.assertTrue(has_next_page)
