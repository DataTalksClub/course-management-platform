import json

from api.tests.review_criteria_api_base import ReviewCriteriaAPITestBase


class ReviewCriteriaAPITestCase(ReviewCriteriaAPITestBase):
    def test_list_empty(self):
        response = self.client.get(self.criteria_url())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["course_slug"], self.course.slug)
        self.assertEqual(data["review_criteria"], [])

    def test_list_returns_criteria(self):
        criteria = self.create_criteria()

        response = self.client.get(self.criteria_url())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["review_criteria"]), 1)
        record = data["review_criteria"][0]
        self.assertEqual(record["id"], criteria.id)
        self.assertEqual(record["description"], "Code quality")
        self.assertEqual(record["review_criteria_type"], "RB")
        self.assertEqual(record["scores_count"], 0)
        self.assertTrue(record["can_delete"])
        self.assertEqual(record["delete_blockers"], [])

    def test_detail(self):
        criteria = self.create_criteria()

        response = self.client.get(self.criteria_url(criteria.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], criteria.id)
        self.assertEqual(len(data["options"]), 2)

    def test_detail_not_found(self):
        response = self.client.get(self.criteria_url(9999))

        self.assertEqual(response.status_code, 404)

    def test_create_criteria(self):
        url = self.criteria_url()
        request_body = json.dumps(self.criteria_payload())

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        record = data["created"][0]
        self.assertEqual(record["description"], "Code quality")
        self.assertEqual(record["review_criteria_type"], "RB")
        self.assertTrue(record["can_delete"])

    def test_create_criteria_bulk(self):
        payload = [
            self.criteria_payload(description="First"),
            self.criteria_payload(
                description="Second",
                review_criteria_type="CB",
            ),
        ]
        url = self.criteria_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 2)

    def test_create_criteria_missing_description(self):
        payload = self.criteria_payload()
        del payload["description"]
        url = self.criteria_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_criteria_invalid_type(self):
        payload = self.criteria_payload(review_criteria_type="XX")
        url = self.criteria_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_criteria_invalid_options(self):
        payload = self.criteria_payload(
            options=[{"criteria": "No score here"}]
        )
        url = self.criteria_url()
        request_body = json.dumps(payload)

        response = self.client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
