from courses.models import Homework
from api.tests.homework_api_base import HomeworkAPITestBase


class HomeworkAuthAPITestCase(HomeworkAPITestBase):
    def test_homework_mutations_require_staff_token(self):
        homework = self._create_homework(slug="staff-only-hw")
        client = self._non_staff_client("homework-nonstaff")
        responses = self._non_staff_homework_mutation_responses(
            client, homework
        )

        for response in responses:
            self._assert_staff_token_required(response)

        nonstaff_homework_exists = Homework.objects.filter(
            course=self.course,
            slug="nonstaff-put",
        ).exists()
        self.assertFalse(nonstaff_homework_exists)
        homework.refresh_from_db()
        self.assertEqual(homework.description, "Description")
        persisted_homework_exists = Homework.objects.filter(
            id=homework.id
        ).exists()
        self.assertTrue(persisted_homework_exists)
