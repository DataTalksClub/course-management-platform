from django.urls import reverse

from courses.models import ProjectState
from courses.tests.course_view_base import (
    CourseDetailViewTestBase,
    credentials,
)


class CourseProjectDisplayTest(CourseDetailViewTestBase):
    def test_logged_out_course_page_prompts_for_submission_status(self):
        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Not submitted")
        self.assertContains(response, "Log in to see submission status")

    def test_course_view_with_completed_projects(self):
        self.client.login(**credentials)
        course_url = reverse("course", args=[self.course.slug])
        response = self.client.get(course_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertTrue(response.context["has_completed_projects"])
        self.assertContains(response, "See all submitted projects")

        completed_project = next(
            project
            for project in response.context["projects"]
            if project.slug == self.completed_project.slug
        )
        self.assertTrue(completed_project.submitted)
        self.assertNotEqual(
            completed_project.badge_state_name,
            "Not submitted",
        )
        self.assertContains(response, completed_project.badge_state_name)

    def test_course_view_without_completed_projects(self):
        self.completed_project.state = (
            ProjectState.COLLECTING_SUBMISSIONS.value
        )
        self.completed_project.save()

        self.client.login(**credentials)
        course_url = reverse("course", args=[self.course.slug])
        response = self.client.get(course_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_completed_projects"])
        self.assertNotContains(response, "See all submitted projects")

    def test_project_deadline_display_for_peer_review_state(self):
        pr_project = self.create_peer_review_project()
        self.create_project_submitter(pr_project)

        self.assert_course_page_contains_deadline(
            pr_project.submission_due_date
        )
        self.client.login(**credentials)
        self.assert_course_page_contains_deadline(
            pr_project.submission_due_date
        )
        self.client.logout()
        self.client.login(username="submitted@test.com", password="12345")
        self.assert_course_page_contains_deadline(
            pr_project.peer_review_due_date
        )
