import logging

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Question,
    Submission,
    Answer,
    User,
    QuestionTypes,
    AnswerTypes,
    Enrollment,
)

from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
    fill_correct_answers,
)


from .util import join_possible_answers

logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


class HomeworkScoringTestCase(TestCase):
    def create_answers(self, submission, answers):
        for question, answer_text in zip(self.questions, answers):
            Answer.objects.create(
                submission=submission,
                question=question,
                answer_text=answer_text,
            )

    def create_answers_for_enrollemnt(self, enrollment, answers):
        submission, _ = Submission.objects.get_or_create(
            homework=self.homework,
            student=enrollment.student,
            enrollment=enrollment,
        )
        self.create_answers(submission, answers)

    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() - timedelta(hours=1),
            state=HomeworkState.OPEN.value,
        )

    def create_free_form_question(self, text, answer_type, answer, score):
        return Question.objects.create(
            homework=self.homework,
            text=text,
            correct_answer=answer,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=answer_type,
            scores_for_correct_answer=score,
        )

    def create_choice_question(
        self, text, choices, question_type, answer, score
    ):
        return Question.objects.create(
            homework=self.homework,
            text=text,
            possible_answers=join_possible_answers(choices),
            correct_answer=answer,
            question_type=question_type,
            answer_type=AnswerTypes.EXACT_STRING.value,
            scores_for_correct_answer=score,
        )

    def create_free_form_questions(self):
        return [
            self.create_free_form_question(
                "What is the capital of France?",
                AnswerTypes.EXACT_STRING.value,
                "paris",
                1,
            ),
            self.create_free_form_question(
                "What is 5 multiplied by 3?",
                AnswerTypes.INTEGER.value,
                "15",
                10,
            ),
            self.create_free_form_question(
                "Which gas is most abundant in Earth's atmosphere?",
                AnswerTypes.EXACT_STRING.value,
                "nitrogen",
                100,
            ),
        ]

    def create_choice_questions(self):
        return [
            self.create_choice_question(
                "Is the Earth flat? (yes/no)",
                ["yes", "no"],
                QuestionTypes.MULTIPLE_CHOICE.value,
                "2",
                1000,
            ),
            self.create_choice_question(
                "Water boils at 100 degrees Celsius. (true/false)",
                ["true", "false"],
                QuestionTypes.MULTIPLE_CHOICE.value,
                "1",
                10000,
            ),
            self.create_choice_question(
                "Select the prime numbers: 2, 4, 5, 7, 8",
                ["2", "4", "5", "7", "8"],
                QuestionTypes.CHECKBOXES.value,
                "1,3,4",
                100000,
            ),
        ]

    def create_questions(self):
        return self.create_free_form_questions() + self.create_choice_questions()

    def create_students(self):
        (
            (self.student1, self.enrollment1),
            (self.student2, self.enrollment2),
            (self.student3, self.enrollment3),
            (self.student4, self.enrollment4),
            (self.student5, self.enrollment5),
        ) = [
            self.create_student(name)
            for name in ("s1", "s2", "s3", "s4", "s5")
        ]

    def setUp(self):
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.questions = self.create_questions()
        self.create_students()

    def create_submission(self, student, enrollment):
        return Submission.objects.create(
            homework=self.homework,
            student=student,
            enrollment=enrollment,
        )

    def assert_submission_scores(self, submission, expected_score):
        self.assertEqual(submission.total_score, expected_score)
        self.assertEqual(submission.questions_score, expected_score)
        self.assertEqual(submission.faq_score, 0)
        self.assertEqual(submission.learning_in_public_score, 0)

    def assert_enrollment_total_score(self, enrollment, expected_score):
        enrollment = fetch_fresh(enrollment)
        self.assertEqual(enrollment.total_score, expected_score)

    def scoring_answers_student1(self):
        return [
            "paris",  # Correct
            "15",  # Correct
            "oxygen",  # Incorrect
            "2",  # Correct
            "2",  # Incorrect
            "1,3",  # Partially correct, but 0 score anyway
        ]

    def scoring_answers_student2(self):
        return [
            "london",  # Incorrect
            "20",  # Incorrect
            "nitrogen",  # Correct
            "1",  # Incorrect
            "1",  # Correct
            "1,3,4",  # Correct
        ]

    def scoring_extra_field_answers(self):
        return [
            "berlin",  # Incorrect
            "15",  # Correct
            "oxygen",  # Incorrect
            "2",  # Correct
            "2",  # Incorrect
            "1,3",  # Partially correct
        ]

    def add_extra_submission_fields(self, submission):
        submission.learning_in_public_links = [
            "https://www.linkedin.com/feed/update/urn:li:activity:7142541710064054272/",
            "https://www.linkedin.com/feed/update/urn:li:activity:7141024622870773763/",
            "https://twitter.com/Al_Grigor/status/1685940623012999168",
        ]
        submission.faq_contribution_url = (
            "https://github.com/DataTalksClub/faq/pull/266"
        )
        submission.save()

    def assert_extra_field_scores(self, submission):
        questions_score = 0 + 10 + 0 + 1000 + 0 + 0
        faq_score = 1
        learning_in_public_score = 3
        total_score = (
            questions_score + faq_score + learning_in_public_score
        )
        self.assertEqual(submission.questions_score, questions_score)
        self.assertEqual(submission.faq_score, faq_score)
        self.assertEqual(
            submission.learning_in_public_score,
            learning_in_public_score,
        )
        self.assertEqual(submission.total_score, total_score)
        self.assert_enrollment_total_score(self.enrollment1, total_score)

    def assert_homework_scored(self):
        self.assertEqual(self.homework.is_scored(), True)
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)

    def leaderboard_students(self):
        return [
            (self.student1, self.enrollment1),
            (self.student2, self.enrollment2),
            (self.student3, self.enrollment3),
            (self.student4, self.enrollment4),
            (self.student5, self.enrollment5),
        ]

    def leaderboard_answer_sets(self):
        return [
            ["paris", "15", "nitrogen", "2", "1", "1,3,4"],
            ["london", "20", "nitrogen", "1", "1", "1,3,4"],
            ["paris", "15", "oxygen", "2", "2", "1,3"],
            ["berlin", "15", "oxygen", "1", "2", "1,2,3"],
            ["madrid", "20", "carbon dioxide", "1", "2", "2,3,4"],
        ]

    def leaderboard_expected_scores(self):
        return [111111, 110100, 1011, 10, 0]

    def leaderboard_row(self, student, enrollment, answers, score, position):
        return {
            "student": student,
            "enrollment": enrollment,
            "answers": answers,
            "score": score,
            "leaderboard_position": position,
        }

    def leaderboard_test_data(self):
        return [
            self.leaderboard_row(student, enrollment, answers, score, position)
            for position, ((student, enrollment), answers, score) in enumerate(
                zip(
                    self.leaderboard_students(),
                    self.leaderboard_answer_sets(),
                    self.leaderboard_expected_scores(),
                ),
                start=1,
            )
        ]

    def assert_leaderboard_rows(self, data):
        for row in data:
            enrollment = fetch_fresh(row["enrollment"])
            self.assertEqual(enrollment.total_score, row["score"])
            self.assertEqual(
                enrollment.position_on_leaderboard,
                row["leaderboard_position"],
            )

    def create_student(self, name):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course, student=student
        )
        return student, enrollment

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

        self.create_answers(submission1, self.scoring_answers_student1())
        self.create_answers(submission2, self.scoring_answers_student2())

        status, message = score_homework_submissions(self.homework.id)

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

        self.create_answers(submission1, self.scoring_extra_field_answers())
        self.add_extra_submission_fields(submission1)

        status, _ = score_homework_submissions(self.homework.id)

        self.assertEqual(status, HomeworkScoringStatus.OK)

        self.homework = fetch_fresh(self.homework)
        submission1 = fetch_fresh(submission1)

        self.assertEqual(status, HomeworkScoringStatus.OK)
        self.assert_homework_scored()
        self.assert_extra_field_scores(submission1)

    def test_course_first_homework_scored(self):
        submission1 = Submission.objects.create(
            homework=self.homework,
            student=self.student1,
            enrollment=self.enrollment1,
        )

        answers_student1 = [
            "berlin",  # Inorrect
            "15",  # Correct
            "oxygen",  # Incorrect
            "2",  # Correct
            "2",  # Incorrect
            "1,3",  # Partially correct
        ]

        self.create_answers(submission1, answers_student1)

        self.assertFalse(self.course.first_homework_scored)

        score_homework_submissions(self.homework.id)

        self.course = fetch_fresh(self.course)
        self.assertTrue(self.course.first_homework_scored)

    def test_leaderboard_update(self):
        data = self.leaderboard_test_data()

        for row in data:
            self.create_answers_for_enrollemnt(
                row["enrollment"], row["answers"]
            )

        score_homework_submissions(self.homework.id)

        self.assert_leaderboard_rows(data)

    def test_fill_most_common_answer_as_correct(self):
        question = self.questions[3]
        question.correct_answer = ''
        question.save()

        answers = [
            (self.enrollment1, "1"),
            (self.enrollment2, "1"),
            (self.enrollment3, "2"),
            (self.enrollment4, "1"),
            (self.enrollment5, "2"),
        ]

        for enrollment, answer in answers:
            submission = Submission.objects.create(
                homework=self.homework,
                student=enrollment.student,
                enrollment=enrollment,
            )
            Answer.objects.create(
                submission=submission,
                question=question,
                answer_text=answer,
            )

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        self.assertEqual(question.correct_answer, "1")


    def test_fill_most_common_answer_as_correct_not_updated_when_set(self):
        question = self.questions[3]
        self.assertEqual(question.correct_answer, "2")

        answers = [
            (self.enrollment1, "1"),
            (self.enrollment2, "1"),
            (self.enrollment3, "2"),
            (self.enrollment4, "1"),
            (self.enrollment5, "2"),
        ]

        for enrollment, answer in answers:
            submission = Submission.objects.create(
                homework=self.homework,
                student=enrollment.student,
                enrollment=enrollment,
            )
            Answer.objects.create(
                submission=submission,
                question=question,
                answer_text=answer,
            )

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        # still 2
        self.assertEqual(question.correct_answer, "2")

    def test_fill_most_common_answer_as_correct_updates_zero_based_answer(self):
        question = self.questions[3]
        question.correct_answer = "0"
        question.save()

        answers = [
            (self.enrollment1, "1"),
            (self.enrollment2, "1"),
            (self.enrollment3, "2"),
            (self.enrollment4, "1"),
            (self.enrollment5, "2"),
        ]

        for enrollment, answer in answers:
            submission = Submission.objects.create(
                homework=self.homework,
                student=enrollment.student,
                enrollment=enrollment,
            )
            Answer.objects.create(
                submission=submission,
                question=question,
                answer_text=answer,
            )

        fill_correct_answers(self.homework)

        question = fetch_fresh(question)

        self.assertEqual(question.correct_answer, "1")
