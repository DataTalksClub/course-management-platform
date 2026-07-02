from django.urls import reverse

from courses.tests.course_view_base import CourseDetailViewTestBase


class CourseDetailUnauthenticatedTest(CourseDetailViewTestBase):
    def test_course_detail_unauthenticated_user(self):
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

        expected_titles = []
        homeworks = self.homeworks
        for homework in homeworks:
            expected_titles.append(homework.title)
        context_homeworks = context["homeworks"]
        for hw in context_homeworks:
            self.assertIn(hw.title, expected_titles)
            self.assertFalse(hw.submitted)
            self.assertIsNone(hw.score)
            has_submitted_at = hasattr(hw, "submitted_at")
            self.assertFalse(has_submitted_at)


class CourseDetailAuthenticatedTest(CourseDetailViewTestBase):
    def test_course_detail_authenticated_user(self):
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
        self.enrollment.delete()
        self.course.first_homework_scored = True
        self.course.save(update_fields=["first_homework_scored"])

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assert_course_context(context, authenticated=True)
        self.assert_not_enrolled_homework_summary(response)
        self.assertIsNone(context["total_score"])
        self.assertFalse(context["has_enrollment"])
        self.assert_no_enrollment_profile_links(response)
