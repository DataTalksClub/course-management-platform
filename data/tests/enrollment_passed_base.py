"""Shared fixtures for enrollment pass-threshold helper tests."""

from dataclasses import dataclass

from .enrollment_base import (
    EnrollmentDataAPIBase,
    PassedEnrollmentScenario,
)


@dataclass(frozen=True)
class PassedSubmissionRowsActors:
    user2: object
    user3: object
    enrollment2: object
    enrollment3: object


@dataclass(frozen=True)
class PassedSubmissionRowsContext:
    passed_submissions: list
    user2: object
    user3: object
    enrollment2: object
    enrollment3: object
    project1: object
    project2: object
    project3: object


class PassedSubmissionRowsMixin:
    def append_primary_user_submissions(self, context):
        submission = self.create_project_submission(
            context.project1, self.user, self.enrollment
        )
        context.passed_submissions.append(submission)
        submission = self.create_project_submission(
            context.project2, self.user, self.enrollment
        )
        context.passed_submissions.append(submission)

    def append_other_student_submissions(self, context):
        submission = self.create_project_submission(
            context.project1, context.user2, context.enrollment2
        )
        context.passed_submissions.append(submission)
        submission = self.create_project_submission(
            context.project1, context.user3, context.enrollment3
        )
        context.passed_submissions.append(submission)
        submission = self.create_project_submission(
            context.project2, context.user3, context.enrollment3
        )
        context.passed_submissions.append(submission)
        submission = self.create_project_submission(
            context.project3, context.user3, context.enrollment3
        )
        context.passed_submissions.append(submission)


class PassedEnrollmentScenarioMixin(PassedSubmissionRowsMixin):
    def create_passed_submission_rows(
        self,
        actors,
    ):
        project1 = self.create_test_project("p1", "P1")
        project2 = self.create_test_project("p2", "P2")
        project3 = self.create_test_project("p3", "P3")

        passed_submissions = []
        context = PassedSubmissionRowsContext(
            passed_submissions=passed_submissions,
            user2=actors.user2,
            user3=actors.user3,
            enrollment2=actors.enrollment2,
            enrollment3=actors.enrollment3,
            project1=project1,
            project2=project2,
            project3=project3,
        )
        self.append_primary_user_submissions(context)
        self.append_other_student_submissions(context)
        return passed_submissions

    def get_passed_enrollment_scenario(self):
        user2 = self.create_unsaved_student(
            "student2", "student2@example.com"
        )
        user3 = self.create_unsaved_student(
            "student3", "student3@example.com"
        )
        user4 = self.create_unsaved_student(
            "student4", "student4@example.com"
        )
        enrollment2 = self.create_unsaved_enrollment(2, user2)
        enrollment3 = self.create_unsaved_enrollment(3, user3)
        enrollment4 = self.create_unsaved_enrollment(4, user4)
        actors = PassedSubmissionRowsActors(
            user2=user2,
            user3=user3,
            enrollment2=enrollment2,
            enrollment3=enrollment3,
        )
        passed_submissions = self.create_passed_submission_rows(actors)
        return PassedEnrollmentScenario(
            passed_submissions=passed_submissions,
            enrollment2=enrollment2,
            enrollment3=enrollment3,
            enrollment4=enrollment4,
        )


class PassedEnrollmentTestBase(
    PassedEnrollmentScenarioMixin,
    EnrollmentDataAPIBase,
):
    """Shared base for passed-enrollment helper tests."""
