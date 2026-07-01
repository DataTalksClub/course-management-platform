from courses.models import HomeworkState
from courses.scoring import HomeworkScoringStatus, score_homework_submissions

from .scoring_base import HomeworkScoringBase, fetch_fresh


class HomeworkScoringWorkflowTests(HomeworkScoringBase):
    def test_homework_closed(self):
        self.homework.state = HomeworkState.CLOSED.value
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)

        self.assertEqual(status, HomeworkScoringStatus.FAIL)

    def test_homework_scoring(self):
        submission1 = self.create_submission(
            self.student1, self.enrollment1
        )
        submission2 = self.create_submission(
            self.student2, self.enrollment2
        )

        expected_score1 = 1 + 10 + 0 + 1000 + 0 + 0
        expected_score2 = 0 + 0 + 100 + 0 + 10000 + 100000

        answers_student1 = self.scoring_answers_student1()
        answers_student2 = self.scoring_answers_student2()
        self.create_answers(submission1, answers_student1)
        self.create_answers(submission2, answers_student2)

        status, _ = score_homework_submissions(self.homework.id)

        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = fetch_fresh(self.homework)
        submission1 = fetch_fresh(submission1)
        submission2 = fetch_fresh(submission2)

        self.assertEqual(status, HomeworkScoringStatus.OK)
        self.assert_homework_scored()

        self.assert_submission_scores(submission1, expected_score1)
        self.assert_submission_scores(submission2, expected_score2)

        self.assert_enrollment_total_score(self.enrollment1, expected_score1)
        self.assert_enrollment_total_score(self.enrollment2, expected_score2)

    def test_homework_scoring_extra_fields(self):
        submission1 = self.create_submission(
            self.student1, self.enrollment1
        )

        answers = self.scoring_extra_field_answers()
        self.create_answers(submission1, answers)
        self.add_extra_submission_fields(submission1)

        status, _ = score_homework_submissions(self.homework.id)

        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = fetch_fresh(self.homework)
        submission1 = fetch_fresh(submission1)

        self.assertEqual(status, HomeworkScoringStatus.OK)
        self.assert_homework_scored()
        self.assert_extra_field_scores(submission1)

    def test_course_first_homework_scored(self):
        submission1 = self.create_submission(
            self.student1, self.enrollment1
        )

        answers = self.scoring_extra_field_answers()
        self.create_answers(submission1, answers)

        self.assertFalse(self.course.first_homework_scored)

        score_homework_submissions(self.homework.id)

        self.course = fetch_fresh(self.course)
        self.assertTrue(self.course.first_homework_scored)
