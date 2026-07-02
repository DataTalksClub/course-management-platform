from courses.models import Homework, Submission
from courses.models.homework import HomeworkState
from api.tests.homework_api_base import HomeworkAPITestBase


class HomeworkDeletionAPITestCase(HomeworkAPITestBase):
    def test_delete_homework_closed(self):
        hw = self._create_homework(state=HomeworkState.CLOSED.value)
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        homework_exists = Homework.objects.filter(id=hw.id).exists()
        self.assertFalse(homework_exists)

    def test_delete_homework_not_closed(self):
        hw = self._create_homework(state=HomeworkState.OPEN.value)
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "homework_not_closed")
        homework_exists = Homework.objects.filter(id=hw.id).exists()
        self.assertTrue(homework_exists)

    def test_delete_homework_with_submissions_is_blocked(self):
        hw = self._create_homework(state=HomeworkState.CLOSED.value)
        submission = self._create_homework_submission(hw)

        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete homework with existing submissions",
        )
        self.assertEqual(
            response.json()["code"], "homework_has_submissions"
        )
        self.assertEqual(
            response.json()["details"]["submissions_count"],
            1,
        )
        homework_exists = Homework.objects.filter(id=hw.id).exists()
        submission_exists = Submission.objects.filter(
            id=submission.id
        ).exists()
        self.assertTrue(homework_exists)
        self.assertTrue(submission_exists)

    def test_delete_homework_by_slug_closed_without_submissions(self):
        hw = self._create_homework(slug="draft-hw")

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/homeworks/by-slug/draft-hw/"
        )

        self.assertEqual(response.status_code, 200)
        homework_exists = Homework.objects.filter(id=hw.id).exists()
        self.assertFalse(homework_exists)
