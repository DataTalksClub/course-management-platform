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


def create_project_submission(data):
    return ProjectSubmission.objects.create(
        project=data.project,
        student=data.user,
        enrollment=data.enrollment,
        github_link=f"https://github.com/{data.label}/project",
        commit_id="1234567",
    )


def create_peer_review_reminder_users(test_case):
    reviewer = test_case.create_user("reviewer", "reviewer@example.com")
    opted_out_reviewer = test_case.create_user(
        "opted-out-reviewer",
        "opted-out-reviewer@example.com",
    )
    author = test_case.create_user("author", "author@example.com")
    return PeerReviewReminderUsers(
        reviewer=reviewer,
        opted_out_reviewer=opted_out_reviewer,
        author=author,
    )


def create_peer_review_reminder_enrollments(test_case, course, users):
    reviewer = test_case.create_enrollment(users.reviewer, course)
    opted_out_reviewer = test_case.create_enrollment(
        users.opted_out_reviewer,
        course,
    )
    author = test_case.create_enrollment(users.author, course)
    return PeerReviewReminderEnrollments(
        reviewer=reviewer,
        opted_out_reviewer=opted_out_reviewer,
        author=author,
    )


def create_peer_review_project(course, now):
    return Project.objects.create(
        course=course,
        slug="project-1",
        title="Project 1",
        submission_due_date=now - timedelta(days=1),
        peer_review_due_date=now + timedelta(days=1, hours=14),
        state=ProjectState.PEER_REVIEWING.value,
    )


def create_peer_review_reminder_submissions(
    project,
    users,
    enrollments,
):
    reviewer_data = ProjectSubmissionData(
        project=project,
        user=users.reviewer,
        enrollment=enrollments.reviewer,
        label="reviewer",
    )
    reviewer = create_project_submission(reviewer_data)
    author_data = ProjectSubmissionData(
        project=project,
        user=users.author,
        enrollment=enrollments.author,
        label="author",
    )
    author = create_project_submission(author_data)
    opted_out_data = ProjectSubmissionData(
        project=project,
        user=users.opted_out_reviewer,
        enrollment=enrollments.opted_out_reviewer,
        label="opted-out",
    )
    opted_out_reviewer = create_project_submission(opted_out_data)

    return PeerReviewReminderSubmissions(
        reviewer=reviewer,
        opted_out_reviewer=opted_out_reviewer,
        author=author,
    )


def create_pending_peer_reviews(submissions):
    create_pending_peer_review(
        submissions.author,
        submissions.reviewer,
    )
    create_pending_peer_review(
        submissions.author,
        submissions.opted_out_reviewer,
    )


def create_peer_review_reminder_fixture(test_case, now):
    course = test_case.create_course()
    users = create_peer_review_reminder_users(test_case)
    enrollments = create_peer_review_reminder_enrollments(
        test_case,
        course,
        users,
    )
    project = create_peer_review_project(course, now)
    submissions = create_peer_review_reminder_submissions(
        project,
        users,
        enrollments,
    )
    create_pending_peer_reviews(submissions)
    return PeerReviewReminderFixture(
        project=project,
        reviewer_submission=submissions.reviewer,
        opted_out_submission=submissions.opted_out_reviewer,
    )


def create_pending_peer_review(author_submission, reviewer):
    return PeerReview.objects.create(
        submission_under_evaluation=author_submission,
        reviewer=reviewer,
        state=PeerReviewState.TO_REVIEW.value,
    )


def assert_peer_review_reminder_payload(test_case, payload, expectation):
    test_case.assertEqual(
        payload["list"]["key"],
        "deadline-reminders:peer-review:ml-zoomcamp-2026:project-1:24h",
    )
    members_by_email = test_case.members_by_email(payload)
    member_emails = set(members_by_email)
    test_case.assertEqual(
        member_emails,
        {
            "reviewer@example.com",
            "opted-out-reviewer@example.com",
        },
    )
    test_case.assertEqual(
        members_by_email["reviewer@example.com"]["source_object_key"],
        f"project-submission:{expectation.reviewer_submission.pk}",
    )
    test_case.assertEqual(
        members_by_email["opted-out-reviewer@example.com"][
            "source_object_key"
        ],
        f"project-submission:{expectation.opted_out_submission.pk}",
    )
    test_case.assertEqual(
        payload["idempotency_key"],
        f"deadline-reminder:peer-review:{expectation.project.pk}:24h",
    )
    test_case.assertEqual(
        payload["context"]["action_url"],
        "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval",
    )
