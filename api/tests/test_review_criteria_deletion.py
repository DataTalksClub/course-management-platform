from api.tests.review_criteria_api_base import ReviewCriteriaAPITestBase
from courses.models import ReviewCriteria


class ReviewCriteriaDeletionAPITestCase(ReviewCriteriaAPITestBase):
    def test_delete_criteria(self):
        criteria = self.create_criteria()
        url = self.criteria_url(criteria.id)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertFalse(
            ReviewCriteria.objects.filter(id=criteria.id).exists()
        )

    def test_delete_criteria_with_scores_blocked(self):
        criteria = self.create_scored_criteria()
        url = self.criteria_url(criteria.id)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete criteria with existing scores",
        )
        self.assertEqual(
            response.json()["code"], "criteria_has_scores"
        )
        self.assertEqual(
            response.json()["details"]["scores_count"], 1
        )
        self.assertTrue(
            ReviewCriteria.objects.filter(id=criteria.id).exists()
        )

    def test_list_reports_scores_and_blockers(self):
        criteria = self.create_scored_criteria()

        response = self.client.get(self.criteria_url())

        self.assertEqual(response.status_code, 200)
        record = response.json()["review_criteria"][0]
        self.assertEqual(record["id"], criteria.id)
        self.assertEqual(record["scores_count"], 1)
        self.assertFalse(record["can_delete"])
        self.assertEqual(record["delete_blockers"], ["has_scores"])
