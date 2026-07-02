from dataclasses import dataclass
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from courses.models import (
    Answer,
    AnswerTypes,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
    User,
)

from .util import join_possible_answers


@dataclass(frozen=True)
class FreeFormQuestionData:
    text: str
    answer_type: str
    answer: str
    score: int


@dataclass(frozen=True)
class ChoiceQuestionData:
    text: str
    choices: list[str]
    question_type: str
    answer: str
    score: int


@dataclass(frozen=True)
class LeaderboardRowData:
    student: User
    enrollment: Enrollment
    answers: list[str]
    score: int
    position: int


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


class HomeworkAnswerFixtureMixin:
    def create_answers(self, submission, answers):
        for question, answer_text in zip(self.questions, answers):
            Answer.objects.create(
                submission=submission,
                question=question,
                answer_text=answer_text,
            )

    def create_answers_for_enrollment(self, enrollment, answers):
        submission, _ = Submission.objects.get_or_create(
            homework=self.homework,
            student=enrollment.student,
            enrollment=enrollment,
        )
        self.create_answers(submission, answers)

    def create_answer_for_question(self, enrollment, question, answer_text):
        submission = Submission.objects.create(
            homework=self.homework,
            student=enrollment.student,
            enrollment=enrollment,
        )
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
        )


class HomeworkScoringCourseFixtureMixin:
    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

    def create_homework(self):
        now = timezone.now()
        due_date = now - timedelta(hours=1)
        return Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=due_date,
            state=HomeworkState.OPEN.value,
        )


class HomeworkQuestionFixtureMixin:
    def create_free_form_question(self, data):
        return Question.objects.create(
            homework=self.homework,
            text=data.text,
            correct_answer=data.answer,
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=data.answer_type,
            scores_for_correct_answer=data.score,
        )

    def create_choice_question(self, data):
        possible_answers = join_possible_answers(data.choices)
        return Question.objects.create(
            homework=self.homework,
            text=data.text,
            possible_answers=possible_answers,
            correct_answer=data.answer,
            question_type=data.question_type,
            answer_type=AnswerTypes.EXACT_STRING.value,
            scores_for_correct_answer=data.score,
        )

    def create_free_form_questions(self):
        questions = []
        capital_question = FreeFormQuestionData(
            text="What is the capital of France?",
            answer_type=AnswerTypes.EXACT_STRING.value,
            answer="paris",
            score=1,
        )
        question = self.create_free_form_question(capital_question)
        questions.append(question)
        multiplication_question = FreeFormQuestionData(
            text="What is 5 multiplied by 3?",
            answer_type=AnswerTypes.INTEGER.value,
            answer="15",
            score=10,
        )
        question = self.create_free_form_question(multiplication_question)
        questions.append(question)
        gas_question = FreeFormQuestionData(
            text="Which gas is most abundant in Earth's atmosphere?",
            answer_type=AnswerTypes.EXACT_STRING.value,
            answer="nitrogen",
            score=100,
        )
        question = self.create_free_form_question(gas_question)
        questions.append(question)
        return questions

    def create_choice_questions(self):
        questions = []
        flat_earth_question = ChoiceQuestionData(
            text="Is the Earth flat? (yes/no)",
            choices=["yes", "no"],
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            answer="2",
            score=1000,
        )
        question = self.create_choice_question(flat_earth_question)
        questions.append(question)
        boiling_question = ChoiceQuestionData(
            text="Water boils at 100 degrees Celsius. (true/false)",
            choices=["true", "false"],
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            answer="1",
            score=10000,
        )
        question = self.create_choice_question(boiling_question)
        questions.append(question)
        prime_numbers_question = ChoiceQuestionData(
            text="Select the prime numbers: 2, 4, 5, 7, 8",
            choices=["2", "4", "5", "7", "8"],
            question_type=QuestionTypes.CHECKBOXES.value,
            answer="1,3,4",
            score=100000,
        )
        question = self.create_choice_question(prime_numbers_question)
        questions.append(question)
        return questions

    def create_questions(self):
        free_form_questions = self.create_free_form_questions()
        choice_questions = self.create_choice_questions()
        return free_form_questions + choice_questions


class HomeworkStudentFixtureMixin:
    def create_students(self):
        self.student1, self.enrollment1 = self.create_student("s1")
        self.student2, self.enrollment2 = self.create_student("s2")
        self.student3, self.enrollment3 = self.create_student("s3")
        self.student4, self.enrollment4 = self.create_student("s4")
        self.student5, self.enrollment5 = self.create_student("s5")

    def create_submission(self, student, enrollment):
        return Submission.objects.create(
            homework=self.homework,
            student=student,
            enrollment=enrollment,
        )

    def create_student(self, name):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course, student=student
        )
        return student, enrollment


class HomeworkScoringAssertionMixin:
    def assert_submission_scores(self, submission, expected_score):
        self.assertEqual(submission.total_score, expected_score)
        self.assertEqual(submission.questions_score, expected_score)
        self.assertEqual(submission.faq_score, 0)
        self.assertEqual(submission.learning_in_public_score, 0)

    def assert_enrollment_total_score(self, enrollment, expected_score):
        enrollment = fetch_fresh(enrollment)
        self.assertEqual(enrollment.total_score, expected_score)

    def assert_homework_scored(self):
        homework_is_scored = self.homework.is_scored()
        self.assertEqual(homework_is_scored, True)
        self.assertEqual(self.homework.state, HomeworkState.SCORED.value)


class HomeworkScoringAnswerSetMixin:
    def scoring_answers_student1(self):
        return [
            "paris",
            "15",
            "oxygen",
            "2",
            "2",
            "1,3",
        ]

    def scoring_answers_student2(self):
        return [
            "london",
            "20",
            "nitrogen",
            "1",
            "1",
            "1,3,4",
        ]

    def scoring_extra_field_answers(self):
        return [
            "berlin",
            "15",
            "oxygen",
            "2",
            "2",
            "1,3",
        ]


class HomeworkExtraFieldScoringMixin:
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


class HomeworkLeaderboardFixtureMixin:
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

    def leaderboard_test_data(self):
        data = []
        students = self.leaderboard_students()
        answer_sets = self.leaderboard_answer_sets()
        expected_scores = self.leaderboard_expected_scores()
        for position, row in enumerate(
            zip(students, answer_sets, expected_scores),
            start=1,
        ):
            student, enrollment = row[0]
            answers = row[1]
            score = row[2]
            row_data = LeaderboardRowData(
                student=student,
                enrollment=enrollment,
                answers=answers,
                score=score,
                position=position,
            )
            data.append(row_data)
        return data

    def assert_leaderboard_rows(self, data):
        for row in data:
            enrollment = fetch_fresh(row.enrollment)
            self.assertEqual(enrollment.total_score, row.score)
            self.assertEqual(
                enrollment.position_on_leaderboard,
                row.position,
            )


class HomeworkScoringBase(
    HomeworkAnswerFixtureMixin,
    HomeworkScoringCourseFixtureMixin,
    HomeworkQuestionFixtureMixin,
    HomeworkStudentFixtureMixin,
    HomeworkScoringAssertionMixin,
    HomeworkScoringAnswerSetMixin,
    HomeworkExtraFieldScoringMixin,
    HomeworkLeaderboardFixtureMixin,
    TestCase,
):
    def setUp(self):
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.questions = self.create_questions()
        self.create_students()
