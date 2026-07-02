import json

from api.tests.homework_api_base import HomeworkAPITestBase


class HomeworkDetailAPITestCase(HomeworkAPITestBase):
    def test_get_homework_detail(self):
        hw = self._create_homework()

        response = self.client.get(
            f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], hw.id)
        self.assertEqual(data["slug"], "hw1")
        self.assertTrue(data["can_delete"])


class HomeworkBySlugPatchAPITestCase(HomeworkAPITestBase):
    def test_patch_homework_by_slug(self):
        self._create_homework(slug="hw-by-slug")

        url = (
            f"/api/courses/{self.course.slug}/homeworks/by-slug/"
            "hw-by-slug/"
        )
        patch_payload = {"description": "Updated by slug"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Updated by slug")
        self.assertEqual(data["slug"], "hw-by-slug")


class HomeworkPatchAPITestCase(HomeworkAPITestBase):
    def test_patch_homework_state(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"state": "OP"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "OP")
        hw.refresh_from_db()
        self.assertEqual(hw.state, "OP")

    def test_patch_homework_description(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"description": "Updated"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        hw.refresh_from_db()
        self.assertEqual(hw.description, "Updated")

    def test_patch_homework_invalid_state(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"state": "XX"}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_homework_invalid_field(self):
        hw = self._create_homework()
        url = f"/api/courses/{self.course.slug}/homeworks/{hw.id}/"
        patch_payload = {"id": 999}
        request_body = json.dumps(patch_payload)
        response = self.client.patch(
            url,
            request_body,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
