import logging

from unittest import TestCase
from collections import defaultdict, Counter

from courses.models import ProjectSubmission

from courses.projects import select_random_assignment


logger = logging.getLogger(__name__)


class ProjectActionsUnitTestCase(TestCase):
    def generate_submissions(self, num_submissions):
        submissions = []

        for i in range(num_submissions):
            submission = ProjectSubmission(id=i)
            submissions.append(submission)

        return submissions

    def assignments_by_reviewer(self, assignments):
        grouped = defaultdict(list)
        for assignment in assignments:
            grouped[assignment.reviewer.id].append(assignment)
        return grouped

    def assert_reviewer_assignment_counts(
        self,
        assignments_by_reviewer,
        num_submissions,
    ):
        self.assertEqual(len(assignments_by_reviewer), num_submissions)

    def assert_reviewer_assignments_are_valid(
        self,
        assignments_by_reviewer,
        num_projects_to_review,
    ):
        submission_counter = Counter()

        for reviewer_id, assignments in assignments_by_reviewer.items():
            ids_to_review = set()

            for assignment in assignments:
                submission_id = assignment.submission_under_evaluation.id
                self.assertNotEqual(submission_id, reviewer_id)
                ids_to_review.add(submission_id)
                submission_counter[submission_id] += 1

            self.assertEqual(len(ids_to_review), num_projects_to_review)

        return submission_counter

    def assert_submission_review_counts(
        self,
        submission_counter,
        num_projects_to_review,
    ):
        for _, count in submission_counter.items():
            self.assertEqual(count, num_projects_to_review)

    def test_select_random_assignment(self):
        num_submissions = 10
        num_projects_to_review = 3

        submissions = self.generate_submissions(num_submissions)

        assignments = select_random_assignment(
            submissions=submissions,
            num_projects_to_review=num_projects_to_review,
            seed=1,
        )

        expected_number_of_assignments = (
            num_submissions * num_projects_to_review
        )
        self.assertEqual(
            len(assignments), expected_number_of_assignments
        )

        assignments_by_reviewer = self.assignments_by_reviewer(assignments)
        self.assert_reviewer_assignment_counts(
            assignments_by_reviewer,
            num_submissions,
        )
        submission_counter = self.assert_reviewer_assignments_are_valid(
            assignments_by_reviewer,
            num_projects_to_review,
        )
        self.assert_submission_review_counts(
            submission_counter,
            num_projects_to_review,
        )

    def test_select_random_assignment_3_3(self):
        num_submissions = 3
        num_projects_to_review = 3

        submissions = self.generate_submissions(num_submissions)

        with self.assertRaises(ValueError):
            select_random_assignment(
                submissions=submissions,
                num_projects_to_review=num_projects_to_review,
                seed=1,
            )
