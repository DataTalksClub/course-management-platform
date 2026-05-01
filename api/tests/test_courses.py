import json

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Course, Homework, Project
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState


class CoursesAPITestCase(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"

        self.course = Course.objects.create(
            title="ML Zoomcamp",
            slug="ml-zoomcamp",
            description="Machine Learning course",
        )

    def test_list_courses(self):
        response = self.client.get("/api/courses/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["courses"]), 1)
        self.assertEqual(data["courses"][0]["slug"], "ml-zoomcamp")

    def test_list_courses_requires_auth(self):
        client = Client()
        response = client.get("/api/courses/")
        self.assertEqual(response.status_code, 401)

    def test_create_course(self):
        payload = {
            "slug": "new-course",
            "title": "New Course",
            "description": "Created by API",
            "social_media_hashtag": "newcourse",
            "project_passing_score": 12,
        }

        response = self.client.post(
            "/api/courses/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "new-course")
        self.assertEqual(data["project_passing_score"], 12)
        self.assertTrue(Course.objects.filter(slug="new-course").exists())

    def test_create_course_duplicate_slug(self):
        payload = {
            "slug": self.course.slug,
            "title": "Duplicate",
        }

        response = self.client.post(
            "/api/courses/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "course_slug_exists")

    def test_course_detail(self):
        Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            instructions_url="https://github.com/DataTalksClub/test/blob/main/homework.md",
            due_date=timezone.now(),
            state=HomeworkState.OPEN.value,
        )
        Project.objects.create(
            course=self.course,
            title="Project 1",
            slug="project-1",
            description="",
            instructions_url="https://github.com/DataTalksClub/test/blob/main/project.md",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=ProjectState.CLOSED.value,
        )

        response = self.client.get("/api/courses/ml-zoomcamp/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "ml-zoomcamp")
        self.assertEqual(len(data["homeworks"]), 1)
        self.assertEqual(len(data["projects"]), 1)
        self.assertIn("visible", data)

    def test_patch_course(self):
        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            json.dumps({
                "title": "Updated ML Zoomcamp",
                "visible": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Updated ML Zoomcamp")
        self.assertFalse(data["visible"])
        self.course.refresh_from_db()
        self.assertFalse(self.course.visible)

    def test_patch_course_invalid_field(self):
        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            json.dumps({"slug": "changed"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")

    def test_course_detail_not_found(self):
        response = self.client.get("/api/courses/nonexistent/")
        self.assertEqual(response.status_code, 404)
