import json

from api.tests.review_criteria_api_base import ReviewCriteriaAPITestBase


class ReviewCriteriaUpdatesAPITestCase(ReviewCriteriaAPITestBase):
    def test_patch_description(self):
        criteria = self.create_criteria()
        url = self.criteria_url(criteria.id)
        request_body = json.dumps({"description": "Renamed"})

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "Renamed")
        criteria.refresh_from_db()
        self.assertEqual(criteria.description, "Renamed")

    def test_patch_options(self):
        criteria = self.create_criteria()
        options = [{"criteria": "Only option", "score": 1}]
        url = self.criteria_url(criteria.id)
        request_body = json.dumps({"options": options})

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], options)

    def test_patch_invalid_field(self):
        criteria = self.create_criteria()
        url = self.criteria_url(criteria.id)
        request_body = json.dumps({"course": 1})

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")

    def test_patch_invalid_options(self):
        criteria = self.create_criteria()
        url = self.criteria_url(criteria.id)
        request_body = json.dumps({"options": []})

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_patch_options_blocked_with_scores(self):
        criteria = self.create_scored_criteria()
        url = self.criteria_url(criteria.id)
        request_body = json.dumps(
            {"options": [{"criteria": "Changed", "score": 1}]}
        )

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "criteria_has_scores"
        )

    def test_patch_description_allowed_with_scores(self):
        criteria = self.create_scored_criteria()
        url = self.criteria_url(criteria.id)
        request_body = json.dumps({"description": "Clarified"})

        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "Clarified")
