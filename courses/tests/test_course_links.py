from django.utils import timezone
from django.urls import reverse

from courses.tests.course_view_base import CourseDetailViewTestBase


class CourseDetailLinksTest(CourseDetailViewTestBase):
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
