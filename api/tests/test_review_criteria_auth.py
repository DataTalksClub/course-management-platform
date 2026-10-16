from api.tests.review_criteria_api_base import ReviewCriteriaAPITestBase
from courses.models import ReviewCriteria


class ReviewCriteriaAuthAPITestCase(ReviewCriteriaAPITestBase):
    def test_non_staff_mutations_forbidden(self):
        criteria = self.create_criteria()
        client = self.non_staff_client()

        responses = self.non_staff_mutation_responses(client, criteria)

        self.assertEqual(len(responses), 3)
        for response in responses:
            with self.subTest(
                method=response.request["REQUEST_METHOD"]
            ):
                self.assert_staff_token_required(response)

    def test_non_staff_mutations_change_nothing(self):
        criteria = self.create_criteria()
        client = self.non_staff_client()

        self.non_staff_mutation_responses(client, criteria)

        criteria.refresh_from_db()
        self.assertEqual(criteria.description, "Code quality")
        self.assertEqual(
            ReviewCriteria.objects.filter(
                course=self.course
            ).count(),
            1,
        )
