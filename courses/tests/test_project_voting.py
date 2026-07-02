from dataclasses import dataclass

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


@dataclass(frozen=True)
class ProjectSubmissionFixtureData:
    username: str
    display_name: str
    repo: str
    commit_id: str


class ProjectVotingBase(TestCase):
    def setUp(self):
        self.course = self.create_course()
        self.project = self.create_project()
        self.voter = User.objects.create_user(username="voter")
        self.submission = self.create_initial_submission()

    def create_course(self):
        return Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )

    def create_project(self):
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        return Project.objects.create(
            course=self.course,
            slug="project",
            title="Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_initial_submission(self):
        self.student = User.objects.create_user(username="student")
        self.enrollment = Enrollment.objects.create(
            course=self.course,
            student=self.student,
            display_name="Student",
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            enrollment=self.enrollment,
            github_link="https://github.com/example/project",
            commit_id="abc1234",
        )

    def create_submission(self, data: ProjectSubmissionFixtureData):
        student = User.objects.create_user(username=data.username)
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=student,
            display_name=data.display_name,
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=student,
            enrollment=enrollment,
            github_link=f"https://github.com/example/{data.repo}",
            commit_id=data.commit_id,
        )


    def project_list_url(self):
        return reverse(
            "project_list",
            args=[self.course.slug, self.project.slug],
        )

    def post_vote(self, submission):
        project_list_url = self.project_list_url()
        return self.client.post(
            project_list_url,
            {"submission_id": submission.id},
        )

    def assert_project_vote_count(self, count):
        vote_count = ProjectVote.objects.filter(
            voter=self.voter,
            submission__project=self.project,
        ).count()
        self.assertEqual(vote_count, count)

    def assert_submission_voted(self, submission, voted=True):
        vote_exists = ProjectVote.objects.filter(
            submission=submission
        ).exists()
        self.assertEqual(vote_exists, voted)


class ProjectVotingPageTestCase(ProjectVotingBase):
    def test_project_voting_page_lists_submissions(self):
        self.client.force_login(self.voter)
        project_list_url = self.project_list_url()
        response = self.client.get(project_list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student")
        self.assertContains(response, "0")
        self.assertContains(response, "Vote")


class ProjectVotingActionTestCase(ProjectVotingBase):
    def test_authenticated_user_can_vote_once(self):
        self.client.force_login(self.voter)

        for _ in range(2):
            response = self.post_vote(self.submission)
            self.assertEqual(response.status_code, 302)

        vote_count = ProjectVote.objects.filter(
            submission=self.submission
        ).count()
        self.assertEqual(vote_count, 1)

    def test_user_can_remove_vote(self):
        ProjectVote.objects.create(
            submission=self.submission,
            voter=self.voter,
        )
        self.client.force_login(self.voter)

        project_list_url = self.project_list_url()
        response = self.client.post(
            project_list_url,
            {
                "submission_id": self.submission.id,
                "action": "remove",
            },
        )

        self.assertEqual(response.status_code, 302)
        vote_exists = ProjectVote.objects.filter(
            submission=self.submission
        ).exists()
        self.assertFalse(vote_exists)

    def test_ajax_vote_returns_updated_vote_state(self):
        self.client.force_login(self.voter)

        project_list_url = self.project_list_url()
        response = self.client.post(
            project_list_url,
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


class ProjectVotingLimitTestCase(ProjectVotingBase):
    def create_other_submission(self):
        submission_data = ProjectSubmissionFixtureData(
            username="other-student",
            display_name="Other Student",
            repo="other-project",
            commit_id="def5678",
        )
        return self.create_submission(submission_data)

    def create_third_submission(self):
        submission_data = ProjectSubmissionFixtureData(
            username="third-student",
            display_name="Third Student",
            repo="third-project",
            commit_id="ghi9012",
        )
        return self.create_submission(submission_data)

    def create_fourth_submission(self):
        submission_data = ProjectSubmissionFixtureData(
            username="fourth-student",
            display_name="Fourth Student",
            repo="fourth-project",
            commit_id="jkl3456",
        )
        return self.create_submission(submission_data)

    def test_user_has_three_votes_per_project(self):
        other_submission = self.create_other_submission()
        third_submission = self.create_third_submission()
        fourth_submission = self.create_fourth_submission()
        self.client.force_login(self.voter)

        self.post_vote(self.submission)
        self.post_vote(other_submission)
        self.post_vote(third_submission)
        self.post_vote(fourth_submission)

        self.assert_project_vote_count(3)
        self.assert_submission_voted(self.submission)
        self.assert_submission_voted(other_submission)
        self.assert_submission_voted(third_submission)
        self.assert_submission_voted(fourth_submission, voted=False)


class ProjectVotingAllSubmissionsTestCase(ProjectVotingBase):
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
