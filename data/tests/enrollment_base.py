"""
Shared fixtures for enrollment-related API tests.
"""

import json
import random
from dataclasses import dataclass, field

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Token
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
)


@dataclass(frozen=True)
class PassedProjectSubmissionData:
    project: Project
    student: CustomUser
    enrollment: Enrollment
    commit_id: str


@dataclass(frozen=True)
class PassedEnrollmentExpectation:
    passed_submissions: list[ProjectSubmission]
    min_projects: int
    expected_enrollments: list[Enrollment]
    missing_enrollments: list[Enrollment] = field(default_factory=list)


@dataclass(frozen=True)
class PassedEnrollmentScenario:
    passed_submissions: list[ProjectSubmission]
    enrollment2: Enrollment
    enrollment3: Enrollment
    enrollment4: Enrollment


@dataclass(frozen=True)
class CertificateUpdateExpectation:
    result: dict
    success: bool
    updated_count: int
    error_count: int | None = None


@dataclass(frozen=True)
class CertificateNotificationScenario:
    data: dict
    second_enrollment: Enrollment


class EnrollmentCourseFixtureMixin:
    def require_two_projects_to_pass(self):
        self.course.min_projects_to_pass = 2
        self.course.save()


class EnrollmentUserFixtureMixin:
    def configure_certificate_user(self):
        self.user.email = "student1@example.com"
        self.user.certificate_name = "Student One"
        self.user.save()

    def create_certificate_user(self, username, email, certificate_name):
        return CustomUser.objects.create(
            username=username,
            email=email,
            password="pass",
            certificate_name=certificate_name,
        )

    def create_enrolled_user(self, username, email, **enrollment_kwargs):
        user = CustomUser.objects.create(
            username=username,
            email=email,
            password="password",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
            **enrollment_kwargs,
        )
        return user, enrollment

    def create_other_user(self):
        return CustomUser.objects.create(
            username="otheruser",
            email="other@example.com",
            password="password",
        )


class EnrollmentProjectFixtureMixin:
    def create_saved_project(self, slug, title):
        now = timezone.now()
        submission_due_date = now + timezone.timedelta(days=7)
        peer_review_due_date = now + timezone.timedelta(days=14)
        return Project.objects.create(
            course=self.course,
            slug=slug,
            title=title,
            description="Description",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_passed_project_submission(
        self,
        data: PassedProjectSubmissionData,
    ):
        ProjectSubmission.objects.create(
            project=data.project,
            student=data.student,
            enrollment=data.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id=data.commit_id,
            passed=True,
        )

    def create_test_project(self, slug, title):
        now = timezone.now()
        submission_due_date = now + timezone.timedelta(days=7)
        peer_review_due_date = now + timezone.timedelta(days=14)
        return Project(
            course=self.course,
            slug=slug,
            title=title,
            description="Description",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
        )

    def create_project_submission(self, project, student, enrollment):
        choices = random.choices("0123456789abcdef", k=7)
        commit_id = "".join(choices)
        github_link = f"https://github.com/test{student.username[-1]}"

        return ProjectSubmission(
            project=project,
            student=student,
            enrollment=enrollment,
            github_link=github_link,
            commit_id=commit_id,
            passed=True,
        )

    def create_unsaved_student(self, username, email):
        return CustomUser(
            username=username,
            email=email,
        )

    def create_unsaved_enrollment(self, enrollment_id, student):
        return Enrollment(
            id=enrollment_id,
            student=student,
            course=self.course,
        )


class EnrollmentURLMixin:
    def graduates_url(self):
        return reverse(
            "api_course_graduates",
            kwargs={"course_slug": self.course.slug},
        )

    def certificate_url(self):
        return reverse(
            "api_course_certificates",
            kwargs={"course_slug": self.course.slug},
        )


class EnrollmentCertificateRequestMixin:
    def post_certificates(self, data):
        url = self.certificate_url()
        body = json.dumps(data)
        return self.client.post(
            url,
            body,
            content_type="application/json",
        )

    def certificate_payload(self, certificates):
        return {"certificates": certificates}

    def mixed_certificate_payload(self, second_user, other_user):
        certificates = [
            {
                "email": self.user.email,
                "certificate_path": "/certificates/first.pdf",
            },
            {
                "email": second_user.email,
                "certificate_path": "/certificates/second.pdf",
            },
            {
                "email": "missing@example.com",
                "certificate_path": "/certificates/missing.pdf",
            },
            {
                "email": other_user.email,
                "certificate_path": "/certificates/other.pdf",
            },
            {"email": self.user.email},
        ]
        return self.certificate_payload(certificates)

    def certificate_notification_scenario(self):
        second_user, second_enrollment = self.create_enrolled_user(
            "seconduser",
            "second@example.com",
            certificate_url="/certificates/old.pdf",
        )
        certificates = [
            {
                "email": self.user.email,
                "certificate_path": "/certificates/first.pdf",
            },
            {
                "email": second_user.email,
                "certificate_path": "/certificates/second.pdf",
            },
        ]
        data = self.certificate_payload(certificates)
        return CertificateNotificationScenario(
            data=data,
            second_enrollment=second_enrollment,
        )

    def post_certificates_with_callbacks(self, data):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_certificates(data)
        return response


class EnrollmentCertificateAssertionsMixin:
    def assert_certificate_update_result(
        self,
        data: CertificateUpdateExpectation,
    ):
        self.assertEqual(data.result["success"], data.success)
        self.assertEqual(data.result["updated_count"], data.updated_count)
        if data.error_count is not None:
            self.assertEqual(data.result["error_count"], data.error_count)

    def assert_certificate_url(self, enrollment, certificate_url):
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.certificate_url, certificate_url)


class EnrollmentDataAPIBase(
    EnrollmentCourseFixtureMixin,
    EnrollmentUserFixtureMixin,
    EnrollmentProjectFixtureMixin,
    EnrollmentURLMixin,
    EnrollmentCertificateRequestMixin,
    EnrollmentCertificateAssertionsMixin,
    TestCase,
):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )
