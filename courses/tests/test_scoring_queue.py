"""Async scoring path: enqueue dedupes, the worker scores, retries skip."""

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from courses.models import (
    Answer,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
    Question,
    AnswerTypes,
    QuestionTypes,
    User,
)
from courses.models.scoring_job import ScoringJob, ScoringJobKind, ScoringJobStatus
from courses.scoring_queue import (
    enqueue_homework_scoring,
    enqueue_project_scoring,
)
from data.management.commands.check_cmp_workers import worker_alarms


def make_user(username):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="x"
    )


class HomeworkScoringQueueTests(TestCase):
    def setUp(self):
        self.student = make_user("hw-student")
        self.course = Course.objects.create(
            slug="hw-course", title="HW", description="d"
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="HW1",
            due_date=timezone.now() - timedelta(hours=1),
            state=HomeworkState.OPEN.value,
        )
        self.question = Question.objects.create(
            homework=self.homework,
            text="2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.EXACT_STRING.value,
            correct_answer="4",
            scores_for_correct_answer=2,
        )
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course
        )
        from courses.models import Submission

        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.student,
            enrollment=enrollment,
        )
        Answer.objects.create(
            submission=self.submission,
            question=self.question,
            answer_text="4",
        )

    def test_enqueue_dedupes_while_active(self):
        first, created_first = enqueue_homework_scoring(self.homework)
        second, created_second = enqueue_homework_scoring(self.homework)
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            ScoringJob.objects.filter(homework=self.homework).count(), 1
        )

    def test_worker_scores_and_marks_job_succeeded(self):
        job, _ = enqueue_homework_scoring(self.homework)
        call_command("process_scoring_queue")
        job.refresh_from_db()
        self.assertEqual(job.status, ScoringJobStatus.SUCCEEDED)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, 2)

    def test_retry_after_crash_does_not_double_score(self):
        job, _ = enqueue_homework_scoring(self.homework)
        call_command("process_scoring_queue")
        job.refresh_from_db()
        self.assertEqual(job.status, ScoringJobStatus.SUCCEEDED)

        # Simulate a stale retry of the same job row (crashed after commit).
        ScoringJob.objects.filter(pk=job.pk).update(
            status=ScoringJobStatus.PROCESSING,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        stale = ScoringJob.objects.get(pk=job.pk)
        from courses.management.commands.process_scoring_queue import (
            _already_scored_skip,
        )

        self.assertIsNotNone(_already_scored_skip(stale))
        call_command("process_scoring_queue")
        stale.refresh_from_db()
        self.assertEqual(stale.status, ScoringJobStatus.SUCCEEDED)
        self.assertIn("idempotent skip", stale.result_message)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.total_score, 2)

    def test_run_cmp_job_scoring_updates_job_state(self):
        from data.models import CmpJobState

        enqueue_homework_scoring(self.homework)
        call_command("run_cmp_job", "scoring")
        state = CmpJobState.objects.get(job="scoring")
        self.assertIsNotNone(state.last_success_at)

    def test_stale_pending_job_raises_backlog_alarm(self):
        job, _ = enqueue_homework_scoring(self.homework)
        ScoringJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )
        self.assertIn("scoring:backlog_age", worker_alarms())
        call_command("process_scoring_queue")
        job.refresh_from_db()
        self.assertEqual(job.status, ScoringJobStatus.SUCCEEDED)
        self.assertNotIn("scoring:backlog_age", worker_alarms())


class ProjectScoringQueueTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug="proj-course", title="P", description="d"
        )
        self.course.project_passing_score = 1
        self.course.save()
        self.project = Project.objects.create(
            course=self.course,
            slug="proj1",
            title="Proj1",
            submission_due_date=timezone.now() - timedelta(days=1),
            peer_review_due_date=timezone.now() - timedelta(hours=1),
            state=ProjectState.PEER_REVIEWING.value,
            number_of_peers_to_evaluate=1,
        )
        self.submission_1 = self._submission("p-student-1")
        self.submission_2 = self._submission("p-student-2")
        PeerReview.objects.create(
            submission_under_evaluation=self.submission_1,
            reviewer=self.submission_2,
            state=PeerReviewState.SUBMITTED.value,
        )
        PeerReview.objects.create(
            submission_under_evaluation=self.submission_2,
            reviewer=self.submission_1,
            state=PeerReviewState.SUBMITTED.value,
        )

    def _submission(self, username):
        user = make_user(username)
        enrollment = Enrollment.objects.create(
            student=user, course=self.course
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link=f"https://github.com/{username}/project",
            commit_id="abc123",
        )

    def test_worker_scores_project(self):
        job, created = enqueue_project_scoring(self.project)
        self.assertTrue(created)
        self.assertEqual(job.kind, ScoringJobKind.PROJECT_SCORE)
        call_command("process_scoring_queue")
        job.refresh_from_db()
        self.assertEqual(job.status, ScoringJobStatus.SUCCEEDED)
        self.project.refresh_from_db()
        self.assertEqual(self.project.state, ProjectState.COMPLETED.value)

    def test_second_run_is_idempotent_skip(self):
        job, _ = enqueue_project_scoring(self.project)
        call_command("process_scoring_queue")
        call_command("process_scoring_queue")
        job.refresh_from_db()
        self.assertEqual(job.status, ScoringJobStatus.SUCCEEDED)
        self.assertEqual(
            ScoringJob.objects.filter(project=self.project).count(), 1
        )
        peer_count = PeerReview.objects.filter(
            submission_under_evaluation__project=self.project
        ).count()
        self.assertEqual(peer_count, 2)
