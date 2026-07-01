"""
Tests for enrollment pass-threshold helper logic.
"""

from dataclasses import dataclass

from api.views.enrollment_graduates import get_passed_enrollments

from .enrollment_base import (
    EnrollmentDataAPIBase,
    PassedEnrollmentExpectation,
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


class PassedEnrollmentAPITestCase(EnrollmentDataAPIBase):
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

    def assert_enrollments_for_min_projects(
        self,
        data: PassedEnrollmentExpectation,
    ):
        result = get_passed_enrollments(
            data.passed_submissions,
            data.min_projects,
        )
        self.assertEqual(len(result), len(data.expected_enrollments))
        for enrollment in data.expected_enrollments:
            self.assertIn(enrollment, result)
        for enrollment in data.missing_enrollments:
            self.assertNotIn(enrollment, result)
        return result

    def assert_min_project_boundaries(self, passed_submissions, enrollment3):
        result = get_passed_enrollments(passed_submissions, 4)
        self.assertEqual(len(result), 0)

        result = get_passed_enrollments([], 1)
        self.assertEqual(len(result), 0)

        with self.assertRaises(AssertionError):
            get_passed_enrollments(passed_submissions, 0)

        three_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=passed_submissions,
            min_projects=3,
            expected_enrollments=[enrollment3],
        )
        result = self.assert_enrollments_for_min_projects(
            three_project_expectation
        )
        self.assertEqual(result[0], enrollment3)

    def test_get_passed_enrollments(self):
        scenario = self.get_passed_enrollment_scenario()

        two_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=scenario.passed_submissions,
            min_projects=2,
            expected_enrollments=[self.enrollment, scenario.enrollment3],
            missing_enrollments=[scenario.enrollment2, scenario.enrollment4],
        )
        self.assert_enrollments_for_min_projects(two_project_expectation)
        one_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=scenario.passed_submissions,
            min_projects=1,
            expected_enrollments=[
                self.enrollment,
                scenario.enrollment2,
                scenario.enrollment3,
            ],
            missing_enrollments=[scenario.enrollment4],
        )
        self.assert_enrollments_for_min_projects(one_project_expectation)
        self.assert_min_project_boundaries(
            scenario.passed_submissions, scenario.enrollment3
        )
