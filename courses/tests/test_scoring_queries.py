from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import override_settings

from courses.project_score_calculation import calculate_project_scoring
from courses.project_scoring import _peer_reviews_for_project
from courses.project_scoring import score_project
from courses.project_assignment import ProjectActionStatus
from courses.tests.project_score_base import ProjectEvaluationTestBase
from courses.tests.datamailer_project_score_base import RELAY_SETTINGS
from data.models import DatamailerOutboxEvent


class ProjectScoringQueryTests(ProjectEvaluationTestBase):
    @override_settings(**RELAY_SETTINGS, RELAY_OUTBOX_DISPATCH_IMMEDIATELY=False)
    def test_scoring_outcomes_do_not_query_per_submission(self):
        self.create_reverse_assignments(self.peer_reviews)
        with CaptureQueriesContext(connection) as queries:
            with self.captureOnCommitCallbacks(execute=True):
                status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)
        self.assertEqual(DatamailerOutboxEvent.objects.count(), 8)
        self.assertLessEqual(len(queries), 20)
        self.assertEqual(DatamailerOutboxEvent.objects.filter(
            event_type="recipient_list.member_remove",
        ).count(), 4)
        removed = DatamailerOutboxEvent.objects.filter(
            event_type="recipient_list.member_remove",
        ).first()
        self.assertEqual(removed.payload["member_payload"]["member"]["status"], "removed")

    @override_settings(**RELAY_SETTINGS, RELAY_OUTBOX_DISPATCH_IMMEDIATELY=False)
    def test_passed_outcome_retains_final_scores_and_upsert(self):
        self.course.project_passing_score = 3
        self.course.save()
        reverse_reviews = self.create_reverse_assignments(self.peer_reviews)
        for review in reverse_reviews:
            self.submit_peer_review(review, "4")
        self.submit_score_answers([("4", 3)] * 3)
        with self.captureOnCommitCallbacks(execute=True):
            status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)
        event = DatamailerOutboxEvent.objects.get(
            event_type="recipient_list.member_upsert",
            idempotency_key__contains=":@passed:",
            payload__object_id=self.submission.pk,
        )
        metadata = event.payload["member_payload"]["member"]["metadata"]
        self.assertTrue(metadata["passed"])
        self.assertEqual(metadata["project_score"], 3)
        self.assertEqual(metadata["total_score"], 33)

    def test_system_answers_are_loaded_once_for_all_submissions(self):
        # Reverse assignments ensure all four submissions are scored.
        self.create_reverse_assignments(self.peer_reviews)
        with CaptureQueriesContext(connection) as queries:
            calculation = calculate_project_scoring(
                self.project, _peer_reviews_for_project(self.project)
            )
        self.assertEqual(len(calculation.submissions_to_update), 4)
        system_answer_reads = [
            query for query in queries
            if query["sql"].startswith("SELECT")
            and '"courses_systemevaluationcriteriaresponse"' in query["sql"]
        ]
        self.assertEqual(len(system_answer_reads), 1)
        self.assertLessEqual(len(queries), 5)
