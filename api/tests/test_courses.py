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

    def test_course_detail(self):
        hw = Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            due_date=timezone.now(),
            state=HomeworkState.OPEN.value,
        )
        proj = Project.objects.create(
            course=self.course,
            title="Project 1",
            slug="project-1",
            description="",
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

    def test_course_detail_not_found(self):
        response = self.client.get("/api/courses/nonexistent/")
        self.assertEqual(response.status_code, 404)
