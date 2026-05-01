from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from api.openapi import (
    build_openapi_spec,
    route_coverage,
    routed_paths,
    routed_url_names,
)


class OpenAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()

    def test_openapi_requires_auth(self):
        response = self.client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 401)

    def test_openapi_schema_endpoint(self):
        response = self.client.get(
            "/api/openapi.json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["openapi"], "3.1.0")
        self.assertIn("/api/courses/", data["paths"])
        self.assertIn("TokenAuth", data["components"]["securitySchemes"])
        self.assertEqual(data["x-route-coverage"]["undocumented"], [])

    def test_all_api_routes_are_documented(self):
        spec = build_openapi_spec()
        documented_names = {
            operation["x-django-url-name"]
            for methods in spec["paths"].values()
            for operation in methods.values()
        }
        self.assertEqual(routed_url_names(), documented_names)

    def test_documented_paths_match_routed_paths(self):
        spec = build_openapi_spec()
        coverage = route_coverage(spec["paths"])

        self.assertEqual(coverage["undocumented"], [])
        self.assertEqual(coverage["documented_without_route"], [])
        self.assertEqual(routed_paths(), set(spec["paths"]))

    def test_data_routes_are_documented(self):
        spec = build_openapi_spec()

        self.assertIn("/api/health/", spec["paths"])
        self.assertIn(
            "/api/courses/{course_slug}/certificates",
            spec["paths"],
        )
        self.assertIn(
            "/api/courses/{course_slug}/graduates",
            spec["paths"],
        )

    def test_slug_upsert_routes_are_documented(self):
        spec = build_openapi_spec()

        homework_methods = spec["paths"][
            "/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/"
        ]
        project_methods = spec["paths"][
            "/api/courses/{course_slug}/projects/by-slug/{project_slug}/"
        ]

        self.assertIn("put", homework_methods)
        self.assertIn("put", project_methods)

    def test_delete_safety_rules_are_documented(self):
        spec = build_openapi_spec()

        homework_delete = spec["paths"][
            "/api/courses/{course_slug}/homeworks/{homework_id}/"
        ]["delete"]
        project_delete = spec["paths"][
            "/api/courses/{course_slug}/projects/{project_id}/"
        ]["delete"]
        question_delete = spec["paths"][
            "/api/courses/{course_slug}/homeworks/{homework_id}/"
            "questions/{question_id}/"
        ]["delete"]

        self.assertIn("no submissions", homework_delete["description"])
        self.assertIn("no submissions", project_delete["description"])
        self.assertIn("no answers", question_delete["description"])
