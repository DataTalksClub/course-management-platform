from datetime import timedelta
from time import perf_counter

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from courses.models import (
    Answer, AnswerTypes, Course, Enrollment, Homework, Question,
    QuestionTypes, Submission, User, PeerReview, Project, ProjectSubmission,
)
from courses.project_assignment import assign_peer_reviews_for_project, ProjectActionStatus
from courses.project_scoring import score_project
from courses.scoring import HomeworkScoringStatus, score_homework_submissions


class HomeworkScoringScaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(
            slug="scale", title="Scale", project_passing_score=1,
        )
        cls.homework = Homework.objects.create(
            course=cls.course, slug="scale", title="Scale",
            due_date=timezone.now() - timedelta(days=1),
        )
        students = User.objects.bulk_create([
            User(username=f"scale-{i}", email=f"scale-{i}@example.invalid")
            for i in range(1200)
        ])
        enrollments = Enrollment.objects.bulk_create([
            Enrollment(course=cls.course, student=student) for student in students
        ])
        cls.submissions = Submission.objects.bulk_create([
            Submission(homework=cls.homework, student=student, enrollment=enrollment)
            for student, enrollment in zip(students, enrollments)
        ])
        questions = Question.objects.bulk_create([
            Question(
                homework=cls.homework, text=f"Question {i}",
                question_type=QuestionTypes.FREE_FORM.value,
                answer_type=AnswerTypes.EXACT_STRING.value,
                correct_answer="yes", scores_for_correct_answer=10,
            ) for i in range(6)
        ])
        Answer.objects.bulk_create([
            Answer(submission=submission, question=question, answer_text="yes")
            for submission in cls.submissions for question in questions
        ])

    def test_1200_submissions_have_bounded_queries_and_final_scores(self):
        started = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            status, _ = score_homework_submissions(self.homework.pk)
        duration = perf_counter() - started
        print(f"SCALE: 1200 submissions / 7200 answers: {duration:.3f}s, {len(queries)} queries")
        self.assertEqual(status, HomeworkScoringStatus.OK)
        selects = [q for q in queries if q["sql"].lstrip().startswith("SELECT")]
        self.assertLessEqual(len(selects), 12)
        self.assertLessEqual(len(queries), 35)
        self.assertEqual(Submission.objects.filter(homework=self.homework, total_score=60).count(), 1200)
        self.assertEqual(Answer.objects.filter(submission__homework=self.homework, is_correct=True).count(), 7200)
        self.assertEqual(Enrollment.objects.filter(course=self.course, total_score=60).count(), 1200)
        positions = list(Enrollment.objects.filter(course=self.course).order_by("id").values_list("position_on_leaderboard", flat=True))
        self.assertEqual(positions, list(range(1, 1201)))

    def test_1200_project_submissions_assignment_and_scoring_queries(self):
        project = Project.objects.create(
            course=self.course, title="Scale project", slug="scale",
            submission_due_date=timezone.now() - timedelta(days=2),
            peer_review_due_date=timezone.now() - timedelta(days=1),
        )
        ProjectSubmission.objects.bulk_create([
            ProjectSubmission(
                project=project, student_id=s.student_id,
                enrollment_id=s.enrollment_id,
                github_link="https://example.invalid/project", commit_id="test",
            ) for s in self.submissions
        ])
        with CaptureQueriesContext(connection) as queries:
            status, _ = assign_peer_reviews_for_project(project)
        self.assertEqual(status, ProjectActionStatus.OK)
        self.assertLessEqual(len(queries), 50)
        reviews = list(PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        ).values_list("reviewer_id", "submission_under_evaluation_id"))
        self.assertEqual(len(reviews), 3600)
        self.assertEqual(len(set(reviews)), 3600)
        self.assertTrue(all(reviewer != target for reviewer, target in reviews))
        project.peer_review_due_date = timezone.now() - timedelta(days=1)
        project.save()
        with CaptureQueriesContext(connection) as queries:
            status, _ = score_project(project)
        self.assertEqual(status, ProjectActionStatus.OK)
        self.assertLessEqual(len(queries), 50)
        self.assertEqual(ProjectSubmission.objects.filter(project=project).count(), 1200)
