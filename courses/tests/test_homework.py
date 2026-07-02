from django.urls import reverse

from courses.tests.homework_view_base import (
    HomeworkDetailViewTestBase,
)

class HomeworkDetailViewTests(HomeworkDetailViewTestBase):

    def test_homework_detail_unauthenticated(self):
        response = self.get_homework_response()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=False
        )
        self.assert_empty_question_answers(context["question_answers"])

        self.assertContains(response, "Shown in your timezone.")
        self.assertNotContains(response, "account timezone")

    def test_homework_detail_unauthenticated_hides_submission_fields(self):
        self.enable_all_optional_submission_fields()

        response = self.get_homework_response()

        self.assertEqual(response.status_code, 200)
        self.assert_unauthenticated_submission_preview(response)
        self.assert_submission_fields_hidden(response)

    def test_homework_detail_displays_optional_instructions_url(self):
        self.homework.instructions_url = (
            "https://github.com/DataTalksClub/course-management-platform/"
            "blob/main/README.md"
        )
        self.homework.save()

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instructions")
        self.assertContains(response, self.homework.instructions_url)
        self.assertContains(response, "fab fa-github")

    def test_homework_detail_hides_missing_instructions_url(self):
        self.homework.instructions_url = ""
        self.homework.save()

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Instructions")

    def test_homework_detail_authenticated_no_submission(self):
        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=True
        )
        self.assertContains(response, "account timezone")
        self.assertContains(
            response,
            f'{reverse("account_settings")}#display-preferences-section',
        )

        self.assert_empty_question_answers(context["question_answers"])
        self.assertContains(response, "Status: Not saved yet")
        self.assertContains(response, "Save submission")
        self.assertContains(
            response,
            (
                "You can save partial answers and update them until the "
                "deadline. Your latest saved version will be scored."
            ),
        )

    def test_homework_detail_authenticated_with_submission(self):
        self.create_submission_with_answers()

        response = self.get_homework_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = self.assert_homework_context(
            response, is_authenticated=True
        )
        self.assertEqual(context["submission"], self.submission)

        self.assert_saved_question_answers(context["question_answers"])
        self.assertContains(response, "Status: Last saved at")
        self.assertContains(response, "Update submission")
        self.assertContains(
            response,
            (
                "You can save partial answers and update them until the "
                "deadline. Your latest saved version will be scored."
            ),
        )
