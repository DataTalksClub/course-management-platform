from dataclasses import dataclass, field
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Project,
    ProjectSubmission,
    Submission,
    User,
)
from courses.wrapped_statistics.calculator import calculate_wrapped_statistics


def in_2025(month=6, day=1):
    naive_date = datetime(
        year=2025,
        month=month,
        day=day,
        hour=12,
        minute=0,
        second=0,
    )
    return timezone.make_aware(naive_date)


@dataclass(frozen=True)
class EnrollmentFixtureData:
    user: User
    display_name: str
    total_score: int
    certificate_url: str = ""


@dataclass(frozen=True)
class HomeworkSubmissionFixtureData:
    user: User
    enrollment: Enrollment
    lecture_hours: float
    homework_hours: float
    learning_links: list[str] = field(default_factory=list)
    faq_url: str = ""


class WrappedModelFactoryMixin:
    def create_course(self):
        return Course.objects.create(
            slug="wrapped-course", title="Wrapped Course"
        )

    def create_homework(self):
        due_date = in_2025()
        return Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="HW 1",
            due_date=due_date,
        )

    def create_project(self):
        submission_due_date = in_2025(7, 1)
        peer_review_due_date = in_2025(7, 8)
        return Project.objects.create(
            course=self.course,
            slug="proj1",
            title="Project 1",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_user(self, email):
        return User.objects.create_user(username=email, email=email)

    def create_enrollment(self, data: EnrollmentFixtureData):
        return Enrollment.objects.create(
            student=data.user,
            course=self.course,
            display_name=data.display_name,
            total_score=data.total_score,
            certificate_url=data.certificate_url,
        )


class WrappedSubmissionFactoryMixin:
    def create_homework_submission(
        self,
        data: HomeworkSubmissionFixtureData,
    ):
        submitted_at = in_2025()
        return Submission.objects.create(
            homework=self.homework,
            student=data.user,
            enrollment=data.enrollment,
            time_spent_lectures=data.lecture_hours,
            time_spent_homework=data.homework_hours,
            learning_in_public_links=data.learning_links,
            faq_contribution_url=data.faq_url,
            submitted_at=submitted_at,
        )

    def create_project_submission(self, user, enrollment):
        submitted_at = in_2025(7, 2)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            time_spent=5.0,
            learning_in_public_links=["https://x/3"],
            submitted_at=submitted_at,
        )


class WrappedActivityFixtureMixin(
    WrappedModelFactoryMixin,
    WrappedSubmissionFactoryMixin,
):
    def create_alice_activity(self):
        self.alice = self.create_user("alice@test.com")
        enrollment_data = EnrollmentFixtureData(
            user=self.alice,
            display_name="Alice",
            total_score=100,
            certificate_url="https://certs.example.com/alice",
        )
        self.alice_enrollment = self.create_enrollment(enrollment_data)
        submission_data = HomeworkSubmissionFixtureData(
            user=self.alice,
            enrollment=self.alice_enrollment,
            lecture_hours=2.0,
            homework_hours=3.0,
            learning_links=["https://x/1", "https://x/2"],
            faq_url="https://faq/alice",
        )
        self.create_homework_submission(submission_data)
        self.create_project_submission(self.alice, self.alice_enrollment)

    def create_bob_activity(self):
        self.bob = self.create_user("bob@test.com")
        enrollment_data = EnrollmentFixtureData(
            user=self.bob,
            display_name="Bob",
            total_score=50,
        )
        self.bob_enrollment = self.create_enrollment(enrollment_data)
        submission_data = HomeworkSubmissionFixtureData(
            user=self.bob,
            enrollment=self.bob_enrollment,
            lecture_hours=1.0,
            homework_hours=1.0,
        )
        self.create_homework_submission(submission_data)


class WrappedStatisticsTestBase(WrappedActivityFixtureMixin, TestCase):
    def setUp(self):
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.project = self.create_project()
        self.create_alice_activity()
        self.create_bob_activity()
        self.stats = calculate_wrapped_statistics(year=2025, force=True)
