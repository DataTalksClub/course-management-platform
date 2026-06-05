from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectVote,
    User,
)


class ProjectVotingTest(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )
        self.project = Project.objects.create(
            course=self.course,
            slug="project",
            title="Project",
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
        )
        self.student = User.objects.create_user(username="student")
        self.voter = User.objects.create_user(username="voter")
        self.enrollment = Enrollment.objects.create(
            course=self.course,
            student=self.student,
            display_name="Student",
        )
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            enrollment=self.enrollment,
            github_link="https://github.com/example/project",
            commit_id="abc1234",
        )

    def test_project_voting_page_lists_submissions(self):
        url = reverse("project_voting", args=[self.course.slug])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student")
        self.assertContains(response, "0 votes")

    def test_authenticated_user_can_vote_once(self):
        self.client.force_login(self.voter)
        url = reverse("project_voting", args=[self.course.slug])

        for _ in range(2):
            response = self.client.post(
                url,
                {"submission_id": self.submission.id},
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(
            ProjectVote.objects.filter(submission=self.submission).count(),
            1,
        )

    def test_user_can_remove_vote(self):
        ProjectVote.objects.create(
            submission=self.submission,
            voter=self.voter,
        )
        self.client.force_login(self.voter)
        url = reverse("project_voting", args=[self.course.slug])

        response = self.client.post(
            url,
            {
                "submission_id": self.submission.id,
                "action": "remove",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProjectVote.objects.filter(submission=self.submission).exists()
        )
