from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Enrollment,
    ProjectState,
)
from courses.tests.course_view_base import (
    CourseDetailViewTestBase,
    OpenHomeworkExpectation,
    ScoredHomeworkExpectation,
    credentials,
)


class CourseDetailViewTests(CourseDetailViewTestBase):

    def test_course_detail_unauthenticated_user(self):
        # Test the view for an unauthenticated user
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertFalse(context["is_authenticated"])
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertIsNone(context["total_score"])

        # Check the properties of each homework in the context
        expected_titles = []
        homeworks = self.homeworks
        for homework in homeworks:
            expected_titles.append(homework.title)
        context_homeworks = context["homeworks"]
        for hw in context_homeworks:
            self.assertIn(hw.title, expected_titles)
            self.assertFalse(hw.submitted)
            self.assertIsNone(hw.score)
            self.assertFalse(hasattr(hw, "submitted_at"))

    def test_course_detail_shows_registration_url(self):
        self.course.start_date = timezone.localdate() + timezone.timedelta(
            days=7
        )
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.save()

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Register")
        self.assertContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )

    def test_course_detail_shows_github_repo_url(self):
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/test-course"
        )
        self.course.save()

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fab fa-github")
        self.assertContains(response, "GitHub")
        self.assertContains(
            response,
            "https://github.com/DataTalksClub/test-course",
        )

    def test_course_detail_shows_calendar_feed_link(self):
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendar feed")
        self.assertNotContains(response, "primer-button\">Calendar feed")
        self.assertContains(
            response,
            "All deadlines are shown in your timezone.",
        )
        self.assertNotContains(response, "account timezone")
        self.assertNotContains(
            response,
            f'{reverse("account_settings")}#display-preferences-section',
        )
        self.assertContains(
            response,
            reverse(
                "course_calendar",
                kwargs={"course_slug": self.course.slug},
            ),
        )

    def test_course_detail_does_not_show_time_left_for_scored_homework(self):
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already scored")
        self.assertContains(
            response,
            'app-badge-info px-2 py-0.5 text-xs font-semibold uppercase">Scored',
        )
        self.assertNotContains(response, "Scored:")
        self.assertNotContains(
            response,
            f'data-deadline="{self.homework1.due_date.isoformat()}"',
        )

    def test_course_calendar_feed(self):
        url = reverse(
            "course_calendar",
            kwargs={"course_slug": self.course.slug},
        )

        response = self.client.get(url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "text/calendar; charset=utf-8",
        )
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("VERSION:2.0", content)
        self.assertIn("X-WR-CALNAME:Test Course deadlines", content)
        self.assertIn("SUMMARY:Test Course: Submitted Homework deadline", content)
        self.assertIn("SUMMARY:Test Course: Open Project submission deadline", content)
        self.assertIn("SUMMARY:Test Course: Open Project peer review deadline", content)
        self.assertEqual(content.count("BEGIN:VEVENT"), 7)

    def test_course_detail_authenticated_user(self):
        # Test the view for an authenticated user

        total_score = 80
        self.enrollment.total_score = total_score
        self.enrollment.save()

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assert_course_context(context, authenticated=True)
        self.assert_authenticated_homework_summary(response)
        self.assert_enrolled_course_context(response, total_score)

    def test_course_detail_authenticated_user_not_enrolled(self):
        # Test the view for an authenticated user

        self.enrollment.delete()
        self.course.first_homework_scored = True
        self.course.save(update_fields=["first_homework_scored"])

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assert_course_context(context, authenticated=True)
        homeworks = self.homeworks_by_slug(response)

        scored_homework = homeworks["scored-homework"]
        scored_expectation = ScoredHomeworkExpectation(
            homework=scored_homework,
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

        self.assertIsNone(context["total_score"])
        self.assertFalse(context["has_enrollment"])
        self.assert_no_enrollment_profile_links(response)

    def test_course_detail_hides_dashboard_until_first_homework_scored(self):
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Course dashboard")
        self.assertNotContains(
            response,
            reverse("dashboard", kwargs={"course_slug": self.course.slug}),
        )

    def test_course_detail_shows_dashboard_after_first_homework_scored(self):
        self.course.first_homework_scored = True
        self.course.save()
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course dashboard")
        self.assertContains(
            response,
            reverse("dashboard", kwargs={"course_slug": self.course.slug}),
        )

    def test_not_enrolled_but_can_edit_details(self):
        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "enrollment", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        enrollment = form.instance
        self.assertEqual(enrollment.student.id, self.user.id)

    def test_course_view_with_completed_projects(self):
        """Test that the course view shows the 'See all submitted projects' button when there are completed projects"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertTrue(response.context["has_completed_projects"])
        self.assertContains(response, "See all submitted projects")

    def test_course_view_without_completed_projects(self):
        """Test that the course view doesn't show the button when there are no completed projects"""
        # Change the completed project to open state
        self.completed_project.state = (
            ProjectState.COLLECTING_SUBMISSIONS.value
        )
        self.completed_project.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_completed_projects"])
        self.assertNotContains(response, "See all submitted projects")

    def test_homeworks_sorted_by_due_date(self):
        """Test that homeworks are displayed in order of due date."""
        self.create_sorted_homework_fixture()

        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homeworks_in_due_order(response)

        self.client.login(**credentials)
        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homeworks_in_due_order(response)

    def test_project_deadline_display_for_peer_review_state(self):
        """Test that the correct deadline is shown based on submission status when project is in PR state"""
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

    def test_course_view_does_not_auto_enroll(self):
        """Test that visiting the course page does not auto-enroll a user"""
        # Delete the existing enrollment
        self.enrollment.delete()

        # Verify enrollment is deleted
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0)

        # Login and visit the course page
        self.client.login(**credentials)
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify NO enrollment was created
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0,
                        "Course view should not auto-enroll users")
