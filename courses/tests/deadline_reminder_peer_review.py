from dataclasses import dataclass
from datetime import timedelta

from accounts.models import CustomUser
from courses.models import (
    Enrollment,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
)


@dataclass(frozen=True)
class ProjectSubmissionData:
    project: Project
    user: CustomUser
    enrollment: Enrollment
    label: str


@dataclass(frozen=True)
class PeerReviewReminderUsers:
    reviewer: CustomUser
    opted_out_reviewer: CustomUser
    author: CustomUser


@dataclass(frozen=True)
class PeerReviewReminderEnrollments:
    reviewer: Enrollment
    opted_out_reviewer: Enrollment
    author: Enrollment


@dataclass(frozen=True)
class PeerReviewReminderSubmissions:
    reviewer: ProjectSubmission
    opted_out_reviewer: ProjectSubmission
    author: ProjectSubmission


@dataclass(frozen=True)
class PeerReviewReminderFixture:
    project: Project
    reviewer_submission: ProjectSubmission
    opted_out_submission: ProjectSubmission


class PeerReviewReminderTestMixin:
    def create_project_submission(self, data):
        return ProjectSubmission.objects.create(
            project=data.project,
            student=data.user,
            enrollment=data.enrollment,
            github_link=f"https://github.com/{data.label}/project",
            commit_id="1234567",
        )

    def create_peer_review_reminder_users(self):
        reviewer = self.create_user("reviewer", "reviewer@example.com")
        opted_out_reviewer = self.create_user(
            "opted-out-reviewer",
            "opted-out-reviewer@example.com",
        )
        author = self.create_user("author", "author@example.com")
        return PeerReviewReminderUsers(
            reviewer=reviewer,
            opted_out_reviewer=opted_out_reviewer,
            author=author,
        )

    def create_peer_review_reminder_enrollments(self, course, users):
        reviewer = self.create_enrollment(users.reviewer, course)
        opted_out_reviewer = self.create_enrollment(
            users.opted_out_reviewer,
            course,
        )
        author = self.create_enrollment(users.author, course)
        return PeerReviewReminderEnrollments(
            reviewer=reviewer,
            opted_out_reviewer=opted_out_reviewer,
            author=author,
        )

    def create_peer_review_project(self, course, now):
        return Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            submission_due_date=now - timedelta(days=1),
            peer_review_due_date=now + timedelta(days=1, hours=14),
            state=ProjectState.PEER_REVIEWING.value,
        )

    def create_peer_review_reminder_submissions(
        self,
        project,
        users,
        enrollments,
    ):
        reviewer = self.create_peer_review_reminder_submission(
            project,
            users.reviewer,
            enrollments.reviewer,
            "reviewer",
        )
        author = self.create_peer_review_reminder_submission(
            project,
            users.author,
            enrollments.author,
            "author",
        )
        opted_out_reviewer = self.create_peer_review_reminder_submission(
            project,
            users.opted_out_reviewer,
            enrollments.opted_out_reviewer,
            "opted-out",
        )

        return PeerReviewReminderSubmissions(
            reviewer=reviewer,
            opted_out_reviewer=opted_out_reviewer,
            author=author,
        )

    def create_peer_review_reminder_submission(
        self,
        project,
        user,
        enrollment,
        label,
    ):
        submission_data = ProjectSubmissionData(
            project=project,
            user=user,
            enrollment=enrollment,
            label=label,
        )
        return self.create_project_submission(submission_data)

    def create_pending_peer_reviews(self, submissions):
        self.create_pending_peer_review(
            submissions.author,
            submissions.reviewer,
        )
        self.create_pending_peer_review(
            submissions.author,
            submissions.opted_out_reviewer,
        )

    def create_peer_review_reminder_fixture(self, now):
        course = self.create_course()
        users = self.create_peer_review_reminder_users()
        enrollments = self.create_peer_review_reminder_enrollments(
            course,
            users,
        )
        project = self.create_peer_review_project(course, now)
        submissions = self.create_peer_review_reminder_submissions(
            project,
            users,
            enrollments,
        )
        self.create_pending_peer_reviews(submissions)
        return PeerReviewReminderFixture(
            project=project,
            reviewer_submission=submissions.reviewer,
            opted_out_submission=submissions.opted_out_reviewer,
        )

    def create_pending_peer_review(self, author_submission, reviewer):
        return PeerReview.objects.create(
            submission_under_evaluation=author_submission,
            reviewer=reviewer,
            state=PeerReviewState.TO_REVIEW.value,
        )

    def assert_peer_review_reminder_payload(self, payload, expectation):
        self.assertEqual(
            payload["list"]["key"],
            "deadline-reminders:peer-review:ml-zoomcamp-2026:project-1:24h",
        )
        members_by_email = self.members_by_email(payload)
        self.assertEqual(
            set(members_by_email),
            {
                "reviewer@example.com",
                "opted-out-reviewer@example.com",
            },
        )
        self.assertEqual(
            members_by_email["reviewer@example.com"]["source_object_key"],
            f"project-submission:{expectation.reviewer_submission.pk}",
        )
        self.assertEqual(
            members_by_email["opted-out-reviewer@example.com"][
                "source_object_key"
            ],
            f"project-submission:{expectation.opted_out_submission.pk}",
        )
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:peer-review:{expectation.project.pk}:24h",
        )
        self.assertEqual(
            payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval",
        )
