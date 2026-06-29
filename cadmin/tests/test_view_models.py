from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from cadmin.view_models import (
    enrollment_list_data,
    project_submission_list_data,
)
from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
    User,
)


class CadminViewModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def create_user(self, username):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test",
        )

    def create_enrollment(self, username, **overrides):
        defaults = {
            "student": self.create_user(username),
            "course": self.course,
            "display_name": username,
            "total_score": 10,
        }
        defaults.update(overrides)
        return Enrollment.objects.create(**defaults)

    def create_homework_submission(self, enrollment):
        return Submission.objects.create(
            homework=self.homework,
            student=enrollment.student,
            enrollment=enrollment,
            total_score=1,
        )

    def create_project_submission(self, enrollment, **overrides):
        defaults = {
            "project": self.project,
            "student": enrollment.student,
            "enrollment": enrollment,
            "github_link": "https://github.com/test/repo",
            "commit_id": "abc123",
            "total_score": 10,
            "passed": True,
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def assert_item_ids(self, items, expected_items):
        self.assertEqual(
            [item.id for item in items],
            [item.id for item in expected_items],
        )

    def test_project_submission_list_data_filters_statuses(self):
        incomplete = self.create_project_submission(
            self.create_enrollment("incomplete")
        )
        missing_repo = self.create_project_submission(
            self.create_enrollment("missing-repo"),
            github_link="",
        )
        not_passed = self.create_project_submission(
            self.create_enrollment("not-passed"),
            passed=False,
        )
        reviewed_submission = self.create_project_submission(
            self.create_enrollment("reviewed")
        )
        PeerReview.objects.create(
            submission_under_evaluation=reviewed_submission,
            reviewer=incomplete,
            note_to_peer="Please review",
            state=PeerReviewState.TO_REVIEW.value,
        )

        submissions, counts = project_submission_list_data(
            self.project,
            "",
            "incomplete-reviews",
        )

        self.assert_item_ids(submissions, [incomplete])
        self.assertEqual(
            counts,
            {
                "all": 4,
                "incomplete_reviews": 1,
                "missing_repository": 1,
                "unscored": 0,
                "not_passed": 1,
            },
        )

        submissions, _ = project_submission_list_data(
            self.project,
            "",
            "missing-repository",
        )
        self.assert_item_ids(submissions, [missing_repo])

        submissions, _ = project_submission_list_data(
            self.project,
            "",
            "not-passed",
        )
        self.assert_item_ids(submissions, [not_passed])

    def test_enrollment_list_data_filters_statuses(self):
        lip_disabled = self.create_enrollment(
            "lip-disabled",
            disable_learning_in_public=True,
        )
        zero_score = self.create_enrollment("zero-score", total_score=0)
        hidden = self.create_enrollment(
            "hidden",
            display_on_leaderboard=False,
        )
        no_submissions = self.create_enrollment(
            "no-submissions",
            total_score=5,
        )
        for enrollment in (lip_disabled, zero_score, hidden):
            self.create_homework_submission(enrollment)

        enrollments, counts = enrollment_list_data(
            self.course,
            "",
            "no-submissions",
        )

        self.assert_item_ids(enrollments, [no_submissions])
        self.assertEqual(
            counts,
            {
                "all": 4,
                "lip_disabled": 1,
                "zero_score": 1,
                "hidden": 1,
                "no_submissions": 1,
            },
        )

        enrollments, _ = enrollment_list_data(
            self.course,
            "",
            "lip-disabled",
        )
        self.assert_item_ids(enrollments, [lip_disabled])

        enrollments, _ = enrollment_list_data(
            self.course,
            "",
            "hidden",
        )
        self.assert_item_ids(enrollments, [hidden])
