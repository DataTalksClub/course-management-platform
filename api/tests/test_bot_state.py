from allauth.socialaccount.models import SocialAccount
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import CustomUser, Token
from courses.models import Course, Enrollment, Homework, Project
from courses.models.project import PeerReview, ProjectSubmission


@override_settings(CMP_BOT_READ_TOKEN="bot-read-secret")
class BotCourseStateTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(slug="ml-2026", title="ML 2026")
        self.project = Project.objects.create(
            course=self.course, slug="project-1", title="Project 1",
            state="PR", submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
        )
        Homework.objects.create(
            course=self.course, slug="hw1", title="Homework 1",
            state="OP", due_date=timezone.now(),
        )
        self.url = "/api/bot/courses/ml-2026/state/"
        self.client.defaults["HTTP_AUTHORIZATION"] = "Bearer bot-read-secret"

    def student(self, name, uid):
        user = CustomUser.objects.create(username=name, email=f"{name}@test.com")
        SocialAccount.objects.create(user=user, provider="slack", uid=uid)
        enrollment = Enrollment.objects.create(student=user, course=self.course)
        return ProjectSubmission.objects.create(
            project=self.project, student=user, enrollment=enrollment,
            github_link="https://github.com/example/project", commit_id="abc",
        )

    def test_course_state_is_current_structured_and_read_only(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["course"]["slug"], "ml-2026")
        self.assertEqual(data["course"]["source_url"], "http://testserver/ml-2026/")
        self.assertEqual(data["homeworks"][0]["state"], "OPEN")
        project = data["projects"][0]
        self.assertEqual(project["state"], "PEER_REVIEWING")
        self.assertTrue(project["peer_review_open"])
        self.assertFalse(project["assignments_created"])
        self.assertIsNone(project["peer_review_opens_at"])
        self.assertEqual(parse_datetime(project["peer_review_due_date"]).replace(microsecond=0), self.project.peer_review_due_date.replace(microsecond=0))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(data["student"], {"mapped": False, "projects": []})
        for state in ("CL", "CS", "CO"):
            self.project.state = state
            self.project.save(update_fields=["state"])
            self.assertFalse(self.client.get(self.url).json()["projects"][0]["peer_review_open"])

    def test_identity_requires_team_and_exact_link_and_only_returns_own_counts(self):
        alice = self.student("alice", "T111_U111")
        bob = self.student("bob", "T222_U111")
        PeerReview.objects.create(reviewer=alice, submission_under_evaluation=bob)
        PeerReview.objects.create(reviewer=bob, submission_under_evaluation=alice)
        PeerReview.objects.create(reviewer=bob, submission_under_evaluation=alice, state="SU")
        data = self.client.get(self.url, {"slack_team_id": "T111", "slack_user_id": "U111"}).json()
        self.assertEqual(data["student"], {"mapped": True, "projects": [{"slug": "project-1", "assigned_count": 1, "pending_count": 1}]})
        self.assertTrue(data["projects"][0]["assignments_created"])
        serialized = str(data)
        for private in ("alice", "bob", "github.com", "T111", "U111", "submission_under_evaluation"):
            self.assertNotIn(private, serialized)
        missing = self.client.get(self.url, {"slack_team_id": "T333", "slack_user_id": "U111"}).json()
        self.assertFalse(missing["student"]["mapped"])
        self.assertEqual(self.client.get(self.url, {"slack_user_id": "U111"}).status_code, 400)

    def test_no_staff_or_missing_or_wrong_token_access(self):
        staff = CustomUser.objects.create(username="staff", is_staff=True)
        token = Token.objects.create(user=staff)
        for value in ("", "Bearer wrong", f"Token {token.key}"):
            self.assertEqual(self.client.get(self.url, HTTP_AUTHORIZATION=value).status_code, 401)
        with override_settings(CMP_BOT_READ_TOKEN=""):
            self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.patch("/api/courses/ml-2026/", {}, content_type="application/json").status_code, 401)

    def test_writes_are_rejected_and_unknown_or_hidden_cohort_not_exposed(self):
        for method in (self.client.post, self.client.patch, self.client.delete):
            self.assertEqual(method(self.url).status_code, 405)
        self.assertEqual(self.client.get("/api/bot/courses/ml-1999/state/").status_code, 404)
        self.course.visible = False
        self.course.save(update_fields=["visible"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
