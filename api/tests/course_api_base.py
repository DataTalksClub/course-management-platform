import json

from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import Course, Homework, Project
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState


class CourseAPITestBase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"

        start_date = timezone.datetime(2026, 1, 15).date()
        end_date = timezone.datetime(2026, 4, 15).date()
        self.course = Course.objects.create(
            title="ML Zoomcamp",
            slug="ml-zoomcamp",
            description="Machine Learning course",
            start_date=start_date,
            end_date=end_date,
            registration_url="https://courses.datatalks.club/ml/register",
            github_repo_url="https://github.com/DataTalksClub/ml-zoomcamp",
        )

    def new_course_payload(self):
        return {
            "slug": "new-course",
            "title": "New Course",
            "description": "Created by API",
            "start_date": "2026-02-01",
            "end_date": "2026-05-01",
            "registration_url": "https://courses.datatalks.club/new",
            "github_repo_url": "https://github.com/DataTalksClub/new",
            "social_media_hashtag": "newcourse",
            "project_passing_score": 12,
        }

    def assert_created_course_payload(self, data):
        self.assertEqual(data["slug"], "new-course")
        self.assertEqual(data["start_date"], "2026-02-01")
        self.assertEqual(data["end_date"], "2026-05-01")
        self.assertEqual(
            data["registration_url"],
            "https://courses.datatalks.club/new",
        )
        self.assertEqual(
            data["github_repo_url"],
            "https://github.com/DataTalksClub/new",
        )
        self.assertEqual(data["project_passing_score"], 12)

    def create_detail_homework(self):
        due_date = timezone.now()
        Homework.objects.create(
            course=self.course,
            title="HW1",
            slug="hw1",
            description="",
            instructions_url="https://github.com/DataTalksClub/test/blob/main/homework.md",
            due_date=due_date,
            state=HomeworkState.OPEN.value,
        )

    def create_detail_project(self):
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        Project.objects.create(
            course=self.course,
            title="Project 1",
            slug="project-1",
            description="",
            instructions_url="https://github.com/DataTalksClub/test/blob/main/project.md",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.CLOSED.value,
        )

    def create_course_detail_fixture(self):
        self.create_detail_homework()
        self.create_detail_project()

    def assert_course_detail_payload(self, data):
        self.assertEqual(data["slug"], "ml-zoomcamp")
        self.assertEqual(data["start_date"], "2026-01-15")
        self.assertEqual(data["end_date"], "2026-04-15")
        self.assertEqual(
            data["registration_url"],
            "https://courses.datatalks.club/ml/register",
        )
        self.assertEqual(
            data["github_repo_url"],
            "https://github.com/DataTalksClub/ml-zoomcamp",
        )
        self.assertEqual(len(data["homeworks"]), 1)
        self.assertEqual(len(data["projects"]), 1)
        self.assertIn("visible", data)

    def patch_course_payload(self):
        return {
            "title": "Updated ML Zoomcamp",
            "start_date": "2026-01-20",
            "end_date": "2026-04-20",
            "registration_url": "https://courses.datatalks.club/updated",
            "github_repo_url": "https://github.com/DataTalksClub/updated",
            "visible": False,
        }

    def assert_patched_course_payload(self, data):
        self.assertEqual(data["title"], "Updated ML Zoomcamp")
        self.assertEqual(data["start_date"], "2026-01-20")
        self.assertEqual(data["end_date"], "2026-04-20")
        self.assertEqual(
            data["registration_url"],
            "https://courses.datatalks.club/updated",
        )
        self.assertEqual(
            data["github_repo_url"],
            "https://github.com/DataTalksClub/updated",
        )
        self.assertFalse(data["visible"])

    def assert_persisted_course_patch(self):
        self.course.refresh_from_db()
        self.assertFalse(self.course.visible)
        self.assertEqual(str(self.course.start_date), "2026-01-20")

    def non_staff_client(self):
        non_staff = CustomUser.objects.create(
            username="nonstaff",
            email="nonstaff@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def non_staff_course_mutation_responses(self, client):
        responses = []
        create_payload = {
            "slug": "nonstaff-course",
            "title": "Nonstaff Course",
        }
        create_body = json.dumps(create_payload)
        create_response = client.post(
            "/api/courses/",
            create_body,
            content_type="application/json",
        )
        responses.append(create_response)

        patch_payload = {"title": "Changed by nonstaff"}
        patch_body = json.dumps(patch_payload)
        patch_response = client.patch(
            "/api/courses/ml-zoomcamp/",
            patch_body,
            content_type="application/json",
        )
        responses.append(patch_response)
        return responses

    def assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def assert_course_unchanged_after_forbidden_mutations(self):
        course_exists = Course.objects.filter(
            slug="nonstaff-course"
        ).exists()
        self.assertFalse(course_exists)
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, "ML Zoomcamp")
