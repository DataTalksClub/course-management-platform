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
        self.client.force_login(self.voter)
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student")
        self.assertContains(response, "0")
        self.assertContains(response, "Vote")

    def test_authenticated_user_can_vote_once(self):
        self.client.force_login(self.voter)
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

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
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

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

    def test_ajax_vote_returns_updated_vote_state(self):
        self.client.force_login(self.voter)
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.post(
            url,
            {"submission_id": self.submission.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["submission_id"], self.submission.id)
        self.assertEqual(data["vote_count"], 1)
        self.assertTrue(data["voted"])
        self.assertEqual(data["votes_left"], 2)
        self.assertFalse(data["vote_limit_reached"])

    def test_user_has_three_votes_per_project(self):
        other_student = User.objects.create_user(username="other-student")
        other_enrollment = Enrollment.objects.create(
            course=self.course,
            student=other_student,
            display_name="Other Student",
        )
        other_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=other_student,
            enrollment=other_enrollment,
            github_link="https://github.com/example/other-project",
            commit_id="def5678",
        )
        third_student = User.objects.create_user(username="third-student")
        third_enrollment = Enrollment.objects.create(
            course=self.course,
            student=third_student,
            display_name="Third Student",
        )
        third_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=third_student,
            enrollment=third_enrollment,
            github_link="https://github.com/example/third-project",
            commit_id="ghi9012",
        )
        fourth_student = User.objects.create_user(username="fourth-student")
        fourth_enrollment = Enrollment.objects.create(
            course=self.course,
            student=fourth_student,
            display_name="Fourth Student",
        )
        fourth_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=fourth_student,
            enrollment=fourth_enrollment,
            github_link="https://github.com/example/fourth-project",
            commit_id="jkl3456",
        )
        self.client.force_login(self.voter)
        url = reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

        self.client.post(url, {"submission_id": self.submission.id})
        self.client.post(url, {"submission_id": other_submission.id})
        self.client.post(url, {"submission_id": third_submission.id})
        self.client.post(url, {"submission_id": fourth_submission.id})

        self.assertEqual(
            ProjectVote.objects.filter(
                voter=self.voter,
                submission__project=self.project,
            ).count(),
            3,
        )
        self.assertTrue(
            ProjectVote.objects.filter(submission=self.submission).exists()
        )
        self.assertTrue(
            ProjectVote.objects.filter(submission=other_submission).exists()
        )
        self.assertTrue(
            ProjectVote.objects.filter(submission=third_submission).exists()
        )
        self.assertFalse(
            ProjectVote.objects.filter(submission=fourth_submission).exists()
        )

    def test_all_project_submissions_shows_votes_without_vote_controls(self):
        ProjectVote.objects.create(
            submission=self.submission,
            voter=self.voter,
        )
        url = reverse("list_all_project_submissions", args=[self.course.slug])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1")
        self.assertNotContains(response, "Voted")
        self.assertNotContains(response, "thumbs-up")
