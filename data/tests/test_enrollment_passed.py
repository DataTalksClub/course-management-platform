"""Tests for enrollment pass-threshold helper logic."""

from api.views.enrollment_graduates import get_passed_enrollments

from .enrollment_base import PassedEnrollmentExpectation
from .enrollment_passed_base import PassedEnrollmentTestBase


def assert_enrollments_for_min_projects(
    test_case,
    data: PassedEnrollmentExpectation,
):
    result = get_passed_enrollments(
        data.passed_submissions,
        data.min_projects,
    )
    test_case.assertEqual(len(result), len(data.expected_enrollments))
    for enrollment in data.expected_enrollments:
        test_case.assertIn(enrollment, result)
    for enrollment in data.missing_enrollments:
        test_case.assertNotIn(enrollment, result)
    return result


class PassedEnrollmentThresholdTestCase(PassedEnrollmentTestBase):
    def test_get_passed_enrollments_for_two_project_minimum(self):
        scenario = self.get_passed_enrollment_scenario()
        expected_enrollments = []
        expected_enrollments.append(self.enrollment)
        expected_enrollments.append(scenario.enrollment3)
        missing_enrollments = []
        missing_enrollments.append(scenario.enrollment2)
        missing_enrollments.append(scenario.enrollment4)
        expectation = PassedEnrollmentExpectation(
            passed_submissions=scenario.passed_submissions,
            min_projects=2,
            expected_enrollments=expected_enrollments,
            missing_enrollments=missing_enrollments,
        )

        assert_enrollments_for_min_projects(self, expectation)

    def test_get_passed_enrollments_for_one_project_minimum(self):
        scenario = self.get_passed_enrollment_scenario()
        expected_enrollments = []
        expected_enrollments.append(self.enrollment)
        expected_enrollments.append(scenario.enrollment2)
        expected_enrollments.append(scenario.enrollment3)
        missing_enrollments = []
        missing_enrollments.append(scenario.enrollment4)
        expectation = PassedEnrollmentExpectation(
            passed_submissions=scenario.passed_submissions,
            min_projects=1,
            expected_enrollments=expected_enrollments,
            missing_enrollments=missing_enrollments,
        )

        assert_enrollments_for_min_projects(self, expectation)


class PassedEnrollmentBoundaryTestCase(PassedEnrollmentTestBase):
    def test_get_passed_enrollments_for_three_project_minimum(self):
        scenario = self.get_passed_enrollment_scenario()
        expected_enrollments = []
        expected_enrollments.append(scenario.enrollment3)
        expectation = PassedEnrollmentExpectation(
            passed_submissions=scenario.passed_submissions,
            min_projects=3,
            expected_enrollments=expected_enrollments,
        )

        result = assert_enrollments_for_min_projects(self, expectation)

        self.assertEqual(result[0], scenario.enrollment3)

    def test_get_passed_enrollments_for_too_many_projects(self):
        scenario = self.get_passed_enrollment_scenario()

        result = get_passed_enrollments(scenario.passed_submissions, 4)

        self.assertEqual(len(result), 0)

    def test_get_passed_enrollments_without_submissions(self):
        result = get_passed_enrollments([], 1)

        self.assertEqual(len(result), 0)

    def test_get_passed_enrollments_rejects_zero_minimum(self):
        scenario = self.get_passed_enrollment_scenario()

        with self.assertRaises(AssertionError):
            get_passed_enrollments(scenario.passed_submissions, 0)
