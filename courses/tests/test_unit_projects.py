import logging

from unittest import TestCase
from collections import defaultdict, Counter

from courses.models import  ProjectSubmission

from courses.projects import select_random_assignment


logger = logging.getLogger(__name__)


class ProjectActionsTestCase(TestCase):
    def test_select_random_assignment(self):
        num_submissions = 10
        num_projects_to_review = 3

        submissions = []

        for i in range(num_submissions):
            submission = ProjectSubmission(id=i)
            submissions.append(submission)

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

        assignments_by_reviewer = defaultdict(list)
        for assignment in assignments:
            reviewer_id = assignment.reviewer.id
            assignments_by_reviewer[reviewer_id].append(assignment)

        self.assertEqual(len(assignments_by_reviewer), num_submissions)

        submission_couner = Counter()

        for reviewer_id, assignments in assignments_by_reviewer.items():
            ids_to_review = set()

            for assignment in assignments:
                submission_id = (
                    assignment.submission_under_evaluation.id
                )

                # the reviewer should not review their own project
                self.assertNotEqual(submission_id, reviewer_id)
                ids_to_review.add(submission_id)

                submission_couner[submission_id] += 1

            # each reviewer gets exactly 3 unique projects to review
            self.assertEqual(len(ids_to_review), num_projects_to_review)

        # each project appears exactly 3 times
        for _, count in submission_couner.items():
            self.assertEqual(count, num_projects_to_review)
