from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from cadmin.views.view_models import (
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


class CadminViewModelBase(TestCase):
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
        item_ids = []
        for item in items:
            item_ids.append(item.id)
        expected_item_ids = []
        for item in expected_items:
            expected_item_ids.append(item.id)
        self.assertEqual(
            item_ids,
            expected_item_ids,
        )


class CadminProjectSubmissionViewModelTests(CadminViewModelBase):
    def create_project_submission_status_examples(self):
        incomplete_enrollment = self.create_enrollment("incomplete")
        incomplete = self.create_project_submission(incomplete_enrollment)
        missing_repo_enrollment = self.create_enrollment("missing-repo")
        missing_repo = self.create_project_submission(
            missing_repo_enrollment,
            github_link="",
        )
        not_passed_enrollment = self.create_enrollment("not-passed")
        not_passed = self.create_project_submission(
            not_passed_enrollment,
            passed=False,
        )
        reviewed_enrollment = self.create_enrollment("reviewed")
        reviewed_submission = self.create_project_submission(reviewed_enrollment)
        PeerReview.objects.create(
            submission_under_evaluation=reviewed_submission,
            reviewer=incomplete,
            note_to_peer="Please review",
            state=PeerReviewState.TO_REVIEW.value,
        )
        return {
            "incomplete": incomplete,
            "missing_repo": missing_repo,
            "not_passed": not_passed,
        }

    def assert_project_submission_filter(self, status_filter, expected_item):
        submissions, _ = project_submission_list_data(
            self.project,
            "",
            status_filter,
        )
        self.assert_item_ids(submissions, [expected_item])

    def test_project_submission_list_data_filters_statuses(self):
        examples = self.create_project_submission_status_examples()

        submissions, counts = project_submission_list_data(
            self.project,
            "",
            "incomplete-reviews",
        )

        self.assert_item_ids(submissions, [examples["incomplete"]])
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
        self.assert_project_submission_filter(
            "missing-repository",
            examples["missing_repo"],
        )
        self.assert_project_submission_filter(
            "not-passed",
            examples["not_passed"],
        )


class CadminEnrollmentViewModelTests(CadminViewModelBase):
    def create_enrollment_status_examples(self):
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
        return {
            "lip_disabled": lip_disabled,
            "hidden": hidden,
            "no_submissions": no_submissions,
        }

    def assert_enrollment_filter(self, status_filter, expected_item):
        enrollments, _ = enrollment_list_data(
            self.course,
            "",
            status_filter,
        )
        self.assert_item_ids(enrollments, [expected_item])

    def test_enrollment_list_data_filters_statuses(self):
        examples = self.create_enrollment_status_examples()

        enrollments, counts = enrollment_list_data(
            self.course,
            "",
            "no-submissions",
        )

        self.assert_item_ids(enrollments, [examples["no_submissions"]])
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
        self.assert_enrollment_filter(
            "lip-disabled",
            examples["lip_disabled"],
        )
        self.assert_enrollment_filter(
            "hidden",
            examples["hidden"],
        )
