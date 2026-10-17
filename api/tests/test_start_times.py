import json

from django.utils.dateparse import parse_datetime

from api.tests.course_api_base import CourseAPITestBase
from courses.models import Homework, Project


class StartTimeAPITests(CourseAPITestBase):
    def test_course_create_exports_start(self):
        payload = self.new_course_payload()
        payload["starts_at"] = "2026-02-01T10:00:00+02:00"
        response = self.client.post(
            "/api/courses/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["starts_at"], "2026-02-01T08:00:00+00:00"
        )

    def test_openapi_starts_are_optional_and_nullable(self):
        schemas = self.client.get("/api/openapi.json").json()[
            "components"
        ]["schemas"]
        for name in ("CourseCreate", "HomeworkCreate", "ProjectCreate"):
            with self.subTest(schema=name):
                schema = schemas[name]
                self.assertNotIn(
                    "starts_at", schema.get("required", [])
                )
                self.assertTrue(
                    schema["properties"]["starts_at"]["nullable"]
                )

    def patch(self, path, data):
        return self.client.patch(
            path, json.dumps(data), content_type="application/json"
        )

    def test_course_start_accepts_offset_and_clears(self):
        path = "/api/courses/ml-zoomcamp/"
        response = self.patch(
            path, {"starts_at": "2026-01-15T10:00:00+02:00"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            parse_datetime(response.json()["starts_at"]),
            parse_datetime("2026-01-15T08:00:00Z"),
        )
        self.assertEqual(
            self.patch(path, {"starts_at": None}).status_code, 200
        )
        self.course.refresh_from_db()
        self.assertIsNone(self.course.starts_at)

    def test_assignment_upsert_and_reschedule(self):
        for kind, model, dates in (
            (
                "homeworks",
                Homework,
                {"due_date": "2026-02-01T00:00:00Z"},
            ),
            (
                "projects",
                Project,
                {
                    "submission_due_date": "2026-02-01T00:00:00Z",
                    "peer_review_due_date": "2026-02-08T00:00:00Z",
                },
            ),
        ):
            with self.subTest(kind=kind):
                path = f"/api/courses/ml-zoomcamp/{kind}/by-slug/first/"
                payload = {
                    "title": "First",
                    "starts_at": "2026-01-20T00:00:00Z",
                    **dates,
                }
                response = self.client.put(
                    path,
                    json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 201)
                self.assertIsNotNone(response.json()["starts_at"])
                invalid = self.patch(
                    path, {"starts_at": "2026-03-01T00:00:00Z"}
                )
                self.assertEqual(invalid.status_code, 400)
                item = model.objects.get(slug="first")
                self.assertEqual(
                    item.starts_at, parse_datetime(payload["starts_at"])
                )
                end_field = next(iter(dates))
                invalid = self.patch(
                    path, {end_field: "2026-01-01T00:00:00Z"}
                )
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(
                    self.patch(path, {"starts_at": None}).status_code,
                    200,
                )

    def test_naive_and_non_string_starts_rejected(self):
        for value in (
            "2026-01-15T10:00:00",
            "2026-01-15",
            123,
            [],
            "bad",
            "0001-01-01T00:00:00+14:00",
        ):
            with self.subTest(value=value):
                response = self.patch(
                    "/api/courses/ml-zoomcamp/", {"starts_at": value}
                )
                self.assertEqual(response.status_code, 400)

    def test_staff_required(self):
        self.user.is_staff = False
        self.user.save()
        response = self.patch(
            "/api/courses/ml-zoomcamp/", {"starts_at": None}
        )
        self.assertEqual(response.status_code, 403)

    def test_course_end_validation_uses_utc_day(self):
        path = "/api/courses/ml-zoomcamp/"
        response = self.patch(
            path, {"starts_at": "2026-04-16T00:30:00+02:00"}
        )
        self.assertEqual(response.status_code, 200)
        response = self.patch(path, {"end_date": "2026-04-14"})
        self.assertEqual(response.status_code, 400)
        self.course.refresh_from_db()
        self.assertEqual(self.course.end_date.isoformat(), "2026-04-15")

    def test_invalid_upsert_does_not_create_assignment(self):
        for kind, model, dates in (
            (
                "homeworks",
                Homework,
                {"due_date": "2026-02-01T00:00:00Z"},
            ),
            (
                "projects",
                Project,
                {
                    "submission_due_date": "2026-02-01T00:00:00Z",
                    "peer_review_due_date": "2026-02-08T00:00:00Z",
                },
            ),
        ):
            for start in (
                "2026-03-01T00:00:00Z",
                "2026-01-01T10:00:00",
                123,
            ):
                with self.subTest(kind=kind, start=start):
                    path = (
                        f"/api/courses/ml-zoomcamp/{kind}/by-slug/bad/"
                    )
                    payload = {
                        "title": "Bad",
                        "starts_at": start,
                        **dates,
                    }
                    response = self.client.put(
                        path,
                        json.dumps(payload),
                        content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(
                        model.objects.filter(slug="bad").exists()
                    )

    def test_bulk_create_validates_and_exposes_start(self):
        for kind, model, dates in (
            (
                "homeworks",
                Homework,
                {"due_date": "2026-02-01T00:00:00Z"},
            ),
            (
                "projects",
                Project,
                {
                    "submission_due_date": "2026-02-01T00:00:00Z",
                    "peer_review_due_date": "2026-02-08T00:00:00Z",
                },
            ),
        ):
            with self.subTest(kind=kind):
                path = f"/api/courses/ml-zoomcamp/{kind}/"
                payload = [
                    {
                        "name": "Good",
                        "starts_at": "2026-01-01T10:00:00+02:00",
                        **dates,
                    },
                    {
                        "name": "Bad",
                        "starts_at": "2026-03-01T00:00:00Z",
                        **dates,
                    },
                ]
                response = self.client.post(
                    path,
                    json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 201)
                data = response.json()
                self.assertEqual(len(data["created"]), 1)
                self.assertEqual(len(data["errors"]), 1)
                self.assertFalse(
                    model.objects.filter(slug="bad").exists()
                )
                item = model.objects.get(slug="good")
                self.assertEqual(
                    item.starts_at,
                    parse_datetime("2026-01-01T08:00:00Z"),
                )
                numeric_path = path + str(item.pk) + "/"
                self.assertEqual(
                    self.patch(
                        numeric_path, {"starts_at": None}
                    ).status_code,
                    200,
                )

    def test_start_preserved_when_omitted_and_exported_in_detail(self):
        self.create_detail_homework()
        homework = Homework.objects.get(slug="hw1")
        homework.starts_at = parse_datetime("2026-01-01T00:00:00Z")
        homework.save()
        path = "/api/courses/ml-zoomcamp/homeworks/by-slug/hw1/"
        self.assertEqual(
            self.patch(path, {"title": "Updated"}).status_code, 200
        )
        data = self.client.get("/api/courses/ml-zoomcamp/").json()
        self.assertEqual(
            data["homeworks"][0]["starts_at"],
            homework.starts_at.isoformat(),
        )

    def test_assignment_staff_and_token_auth_required(self):
        self.create_detail_homework()
        self.create_detail_project()
        self.user.is_staff = False
        self.user.save()
        paths = (
            "/api/courses/ml-zoomcamp/homeworks/by-slug/hw1/",
            "/api/courses/ml-zoomcamp/projects/by-slug/project-1/",
        )
        for path in paths:
            self.assertEqual(
                self.patch(path, {"starts_at": None}).status_code, 403
            )
        del self.client.defaults["HTTP_AUTHORIZATION"]
        self.assertEqual(
            self.patch(paths[0], {"starts_at": None}).status_code, 401
        )
