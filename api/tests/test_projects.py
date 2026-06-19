import json
from datetime import timedelta

from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import (
    Course,
    Enrollment,
    PeerReview,
    Project,
    ProjectSubmission,
)
from courses.models.project import PeerReviewState, ProjectState


PROJECT_INSTRUCTIONS_URL = (
    "https://github.com/DataTalksClub/test/blob/main/project.md"
)


class ProjectsAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            password="password",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def _create_project(
        self, slug="proj1", state=ProjectState.CLOSED.value
    ):
        return Project.objects.create(
            course=self.course,
            title="Project 1",
            slug=slug,
            description="Description",
            instructions_url=PROJECT_INSTRUCTIONS_URL,
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
            state=state,
        )

    def _create_project_submission(self, project, username):
        user = CustomUser.objects.create(
            username=username,
            email=f"{username}@example.com",
            password="password",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        return ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link=f"https://github.com/{username}/project",
            commit_id="abc123",
        )

    def test_list_projects(self):
        self._create_project()
        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["submissions_count"], 0)
        self.assertTrue(data["projects"][0]["can_delete"])

    def test_create_project(self):
        payload = {
            "name": "Project 2",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "instructions_url": PROJECT_INSTRUCTIONS_URL,
        }
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["created"]), 1)
        self.assertEqual(
            data["created"][0]["instructions_url"],
            PROJECT_INSTRUCTIONS_URL,
        )
        self.assertEqual(data["created"][0]["state"], "CL")

    def test_create_project_without_instructions_url(self):
        payload = {
            "name": "Project without instructions",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
        }
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(
            data["created"][0]["title"],
            "Project without instructions",
        )
        self.assertIsNone(data["created"][0]["instructions_url"])

    def test_create_project_bulk(self):
        payload = [
            {
                "name": "P1",
                "submission_due_date": "2026-04-01T23:59:59Z",
                "peer_review_due_date": "2026-04-08T23:59:59Z",
                "instructions_url": PROJECT_INSTRUCTIONS_URL,
            },
            {
                "name": "P2",
                "submission_due_date": "2026-05-01T23:59:59Z",
                "peer_review_due_date": "2026-05-08T23:59:59Z",
                "instructions_url": PROJECT_INSTRUCTIONS_URL,
            },
        ]
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["created"]), 2)

    def test_create_project_missing_fields(self):
        payload = {"name": "No dates"}
        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_project_state(self):
        proj = self._create_project()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/",
            json.dumps({"state": "CS"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        proj.refresh_from_db()
        self.assertEqual(proj.state, "CS")

    def test_get_project_detail(self):
        proj = self._create_project()

        response = self.client.get(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], proj.id)
        self.assertEqual(data["slug"], "proj1")
        self.assertTrue(data["can_delete"])

    def test_patch_project_by_slug(self):
        self._create_project(slug="project-by-slug")

        response = self.client.patch(
            f"/api/courses/{self.course.slug}/projects/by-slug/project-by-slug/",
            json.dumps({"description": "Updated by slug"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["description"], "Updated by slug")
        self.assertEqual(data["slug"], "project-by-slug")

    def test_put_project_by_slug_creates_project(self):
        payload = {
            "name": "Project From Put",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "description": "Created idempotently",
            "instructions_url": PROJECT_INSTRUCTIONS_URL,
        }

        response = self.client.put(
            f"/api/courses/{self.course.slug}/projects/by-slug/project-put/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "project-put")
        self.assertEqual(data["title"], "Project From Put")

    def test_put_project_by_slug_updates_project(self):
        project = self._create_project(slug="project-put")
        payload = {
            "title": "Updated Project",
            "submission_due_date": "2026-04-01T23:59:59Z",
            "peer_review_due_date": "2026-04-08T23:59:59Z",
            "description": "Updated idempotently",
        }

        response = self.client.put(
            f"/api/courses/{self.course.slug}/projects/by-slug/project-put/",
            json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.title, "Updated Project")
        self.assertEqual(project.description, "Updated idempotently")

    def test_put_project_by_slug_missing_create_fields(self):
        response = self.client.put(
            f"/api/courses/{self.course.slug}/projects/by-slug/project-put/",
            json.dumps({"title": "Missing dates"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "missing_required_fields"
        )

    def test_put_project_invalid_state_does_not_create(self):
        response = self.client.put(
            f"/api/courses/{self.course.slug}/projects/by-slug/project-put/",
            json.dumps(
                {
                    "name": "Bad State",
                    "submission_due_date": "2026-04-01T23:59:59Z",
                    "peer_review_due_date": "2026-04-08T23:59:59Z",
                    "instructions_url": PROJECT_INSTRUCTIONS_URL,
                    "state": "XX",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "invalid_project_state"
        )
        self.assertFalse(
            Project.objects.filter(
                course=self.course,
                slug="project-put",
            ).exists()
        )

    def test_patch_project_invalid_state(self):
        proj = self._create_project()
        response = self.client.patch(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/",
            json.dumps({"state": "XX"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_project_closed(self):
        proj = self._create_project(state=ProjectState.CLOSED.value)
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(id=proj.id).exists())

    def test_delete_project_not_closed(self):
        proj = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "project_not_closed")
        self.assertTrue(Project.objects.filter(id=proj.id).exists())

    def test_delete_project_with_submissions_is_blocked(self):
        proj = self._create_project(state=ProjectState.CLOSED.value)
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        submission = ProjectSubmission.objects.create(
            project=proj,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
        )

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/{proj.id}/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Cannot delete project with existing submissions",
        )
        self.assertEqual(
            response.json()["code"], "project_has_submissions"
        )
        self.assertEqual(
            response.json()["details"]["submissions_count"],
            1,
        )
        self.assertTrue(Project.objects.filter(id=proj.id).exists())
        self.assertTrue(
            ProjectSubmission.objects.filter(id=submission.id).exists()
        )

    def test_delete_project_by_slug_closed_without_submissions(self):
        proj = self._create_project(slug="draft-project")

        response = self.client.delete(
            f"/api/courses/{self.course.slug}/projects/by-slug/draft-project/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(id=proj.id).exists())

    def test_assign_project_peer_reviews(self):
        project = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        project.submission_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.number_of_peers_to_evaluate = 2
        project.save()
        for i in range(4):
            self._create_project_submission(project, f"student-{i}")

        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/assign-reviews/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["project_slug"], "proj1")
        self.assertEqual(
            data["state"], ProjectState.PEER_REVIEWING.value
        )
        self.assertEqual(data["assigned_peer_reviews_count"], 8)
        self.assertEqual(data["peer_reviews_count"], 8)

    def test_assign_project_peer_reviews_by_slug_blocked_when_closed(
        self,
    ):
        project = self._create_project(
            slug="closed-project",
            state=ProjectState.CLOSED.value,
        )
        project.submission_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.save()

        response = self.client.post(
            (
                f"/api/courses/{self.course.slug}/projects/by-slug/"
                "closed-project/assign-reviews/"
            )
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["project_slug"], "closed-project")
        self.assertEqual(data["state"], ProjectState.CLOSED.value)
        self.assertEqual(data["assigned_peer_reviews_count"], 0)

    def test_score_project(self):
        self.course.project_passing_score = 1
        self.course.save()
        project = self._create_project(
            state=ProjectState.PEER_REVIEWING.value
        )
        project.peer_review_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.number_of_peers_to_evaluate = 1
        project.save()
        submission_1 = self._create_project_submission(
            project, "score-student-1"
        )
        submission_2 = self._create_project_submission(
            project, "score-student-2"
        )
        PeerReview.objects.create(
            submission_under_evaluation=submission_1,
            reviewer=submission_2,
            state=PeerReviewState.SUBMITTED.value,
        )
        PeerReview.objects.create(
            submission_under_evaluation=submission_2,
            reviewer=submission_1,
            state=PeerReviewState.SUBMITTED.value,
        )

        response = self.client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/score/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["project_slug"], "proj1")
        self.assertEqual(data["state"], ProjectState.COMPLETED.value)
        self.assertEqual(data["submissions_count"], 2)
        self.assertEqual(data["scored_submissions_count"], 2)

    def test_score_project_by_slug_blocked_without_peer_reviews(self):
        self.course.project_passing_score = 1
        self.course.save()
        project = self._create_project(
            slug="no-reviews-project",
            state=ProjectState.PEER_REVIEWING.value,
        )
        project.peer_review_due_date = timezone.now() - timedelta(
            hours=1
        )
        project.save()

        response = self.client.post(
            (
                f"/api/courses/{self.course.slug}/projects/by-slug/"
                "no-reviews-project/score/"
            )
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "FAIL")
        self.assertEqual(data["project_slug"], "no-reviews-project")
        self.assertEqual(
            data["state"], ProjectState.PEER_REVIEWING.value
        )
        self.assertEqual(data["scored_submissions_count"], 0)

    def test_project_actions_require_staff_token(self):
        project = self._create_project(
            state=ProjectState.COLLECTING_SUBMISSIONS.value
        )
        non_staff = CustomUser.objects.create(
            username="project-nonstaff",
            email="project-nonstaff@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        client = Client(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = client.post(
            f"/api/courses/{self.course.slug}/projects/{project.id}/assign-reviews/"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["code"], "staff_token_required"
        )

    def test_project_mutations_require_staff_token(self):
        project = self._create_project(slug="staff-only-project")
        non_staff = CustomUser.objects.create(
            username="project-mutation-nonstaff",
            email="project-mutation-nonstaff@example.com",
            password="password",
        )
        token = Token.objects.create(user=non_staff)
        client = Client(HTTP_AUTHORIZATION=f"Token {token.key}")

        create_response = client.post(
            f"/api/courses/{self.course.slug}/projects/",
            json.dumps({
                "name": "Created by nonstaff",
                "submission_due_date": "2026-04-01T23:59:59Z",
                "peer_review_due_date": "2026-04-08T23:59:59Z",
            }),
            content_type="application/json",
        )
        patch_response = client.patch(
            f"/api/courses/{self.course.slug}/projects/{project.id}/",
            json.dumps({"description": "Changed by nonstaff"}),
            content_type="application/json",
        )
        put_response = client.put(
            (
                f"/api/courses/{self.course.slug}/projects/by-slug/"
                "nonstaff-put/"
            ),
            json.dumps({
                "name": "Put by nonstaff",
                "submission_due_date": "2026-04-01T23:59:59Z",
                "peer_review_due_date": "2026-04-08T23:59:59Z",
            }),
            content_type="application/json",
        )
        delete_response = client.delete(
            f"/api/courses/{self.course.slug}/projects/{project.id}/"
        )

        for response in (
            create_response,
            patch_response,
            put_response,
            delete_response,
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json()["code"], "staff_token_required"
            )

        self.assertFalse(
            Project.objects.filter(
                course=self.course,
                slug="nonstaff-put",
            ).exists()
        )
        project.refresh_from_db()
        self.assertEqual(project.description, "Description")
        self.assertTrue(Project.objects.filter(id=project.id).exists())
