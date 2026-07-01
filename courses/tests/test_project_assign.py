from datetime import timedelta

from django.utils import timezone

from courses.models import PeerReview, ProjectState
from courses.project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)
from courses.tests.project_assign_base import (
    ProjectActionsTestBase,
    fetch_fresh,
)


class ProjectActionsTestCase(ProjectActionsTestBase):
    def test_select_random_assignment(self):
        num_submissions = 10
        self.generate_submissions(num_submissions)

        self.assert_no_peer_reviews()
        self.assertEqual(
            self.project.state,
            ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        status, _ = self.assign_peer_reviews()
        self.assertEqual(status, ProjectActionStatus.OK)

        self.assert_assignment_created(num_submissions)

    def test_assign_sets_peer_review_deadline_to_seven_days_next_hour(self):
        self.project.peer_review_due_date = timezone.now() - timedelta(days=30)
        self.project.save()

        before = timezone.now()
        self.generate_submissions(10)

        status, _ = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)
        after = timezone.now()

        deadline = fetch_fresh(self.project).peer_review_due_date

        self.assertEqual(deadline.minute, 0)
        self.assertEqual(deadline.second, 0)
        self.assertEqual(deadline.microsecond, 0)
        self.assertGreaterEqual(deadline, before + timedelta(days=7))
        self.assertLess(
            deadline, after + timedelta(days=7) + timedelta(hours=1)
        )

    def test_select_random_assignment_3_3(self):
        num_submissions = 3
        self.generate_submissions(num_submissions)

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, message = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.FAIL)

        expected_message = (
            "Not enough submissions to assign 3 peer reviews each."
        )
        self.assertEqual(message, expected_message)

    def test_select_random_assignment_4_3(self):
        num_submissions = 4
        self.generate_submissions(num_submissions)

        self.project.number_of_peers_to_evaluate = 3
        self.project.save()

        status, message = assign_peer_reviews_for_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        )
        peer_review_count = peer_reviews.count()
        self.assertEqual(peer_review_count, 12)
