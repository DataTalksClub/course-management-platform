from dataclasses import dataclass
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    AnswerTypes,
    QuestionTypes,
    Submission,
    Answer,
)


@dataclass(frozen=True)
class AnswerData:
    submission: Submission
    question: Question
    answer_text: str
    is_correct: bool


@dataclass(frozen=True)
class HomeworkSubmissionEditFixture:
    submission: Submission
    question1: Question
    question2: Question


@dataclass(frozen=True)
class HomeworkSubmissionEditPageFixture:
    enrollment: Enrollment
    submission: Submission
    question1: Question
    question2: Question


@dataclass(frozen=True)
class HomeworkSubmissionScoreExpectation:
    submission: Submission
    questions_score: int
    learning_in_public_score: int
    total_score: int


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class HomeworkCadminViewTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.create_test_users()
        self.create_course_work_items()

    def create_test_users(self):
        self.user = User.objects.create_user(**credentials)
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
        )

    def create_course_work_items(self):
        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )
        due_date = timezone.now() + timedelta(days=7)
        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=due_date,
            state=HomeworkState.OPEN.value,
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def create_enrollment(self, student=None):
        student = student or self.user
        return Enrollment.objects.create(
            student=student,
            course=self.course,
        )

    def create_homework_submission(self, enrollment=None, **overrides):
        enrollment = enrollment or self.create_enrollment()
        defaults = {
            "homework": self.homework,
            "student": self.user,
            "enrollment": enrollment,
            "questions_score": 0,
            "faq_score": 0,
            "learning_in_public_score": 0,
            "total_score": 0,
        }
        defaults.update(overrides)
        return Submission.objects.create(**defaults)

    def create_homework_search_submission(self, index):
        user = User.objects.create_user(
            username=f"hw-student-{index:02d}",
            email=f"hw-student-{index:02d}@example.com",
            password="test",
        )
        enrollment = self.create_enrollment(student=user)
        return self.create_homework_submission(
            enrollment=enrollment,
            student=user,
            total_score=index,
        )

    def create_homework_search_submissions(self, count):
        for index in range(count):
            self.create_homework_search_submission(index)

    def create_free_form_question(self, score=1):
        return Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.INTEGER.value,
            correct_answer="4",
            scores_for_correct_answer=score,
        )

    def create_multiple_choice_question(self, **overrides):
        defaults = {
            "homework": self.homework,
            "text": "What is the capital of France?",
            "question_type": QuestionTypes.MULTIPLE_CHOICE.value,
            "possible_answers": "London\nParis\nBerlin",
            "correct_answer": "2",
            "scores_for_correct_answer": 1,
        }
        defaults.update(overrides)
        return Question.objects.create(**defaults)

    def create_homework_answer_submission(
        self,
        question,
        answer_text,
        student_index,
    ):
        user = User.objects.create_user(
            username=f"student{student_index}@test.com",
            email=f"student{student_index}@test.com",
            password="12345",
        )
        enrollment = self.create_enrollment(student=user)
        submission = Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
        )
        return Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
        )

    def create_homework_answer_frequency(self, question, answer_texts):
        for index, answer_text in enumerate(answer_texts, start=1):
            self.create_homework_answer_submission(
                question,
                answer_text,
                index,
            )

    def create_answer(self, data):
        return Answer.objects.create(
            submission=data.submission,
            question=data.question,
            answer_text=data.answer_text,
            is_correct=data.is_correct,
        )

    def create_submission_with_answer_preview(self, answer_text):
        question = Question.objects.create(
            homework=self.homework,
            text="Explain your answer",
            question_type=QuestionTypes.FREE_FORM.value,
        )
        submission = self.create_homework_submission(total_score=1)
        Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
        )
        return submission

    def homework_submission_edit_url(self, submission):
        return reverse(
            "cadmin_homework_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
                "submission_id": submission.id,
            },
        )

    def assert_answer_updated(self, submission, question, answer_text):
        answer = Answer.objects.get(submission=submission, question=question)
        self.assertEqual(answer.answer_text, answer_text)
        self.assertTrue(answer.is_correct)

    def create_homework_submission_edit_page_fixture(self):
        enrollment = self.create_enrollment()
        question1 = self.create_free_form_question()
        question2 = self.create_multiple_choice_question()
        submission = self.create_homework_submission(
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            questions_score=2,
            learning_in_public_score=1,
            total_score=3,
        )
        first_answer = AnswerData(
            submission=submission,
            question=question1,
            answer_text="4",
            is_correct=True,
        )
        self.create_answer(first_answer)
        second_answer = AnswerData(
            submission=submission,
            question=question2,
            answer_text="2",
            is_correct=True,
        )
        self.create_answer(second_answer)
        return HomeworkSubmissionEditPageFixture(
            enrollment=enrollment,
            submission=submission,
            question1=question1,
            question2=question2,
        )

    def create_homework_submission_edit_fixture(self):
        enrollment = self.create_enrollment()
        question1 = self.create_free_form_question()
        question2 = self.create_multiple_choice_question()
        submission = self.create_homework_submission(
            enrollment=enrollment,
            learning_in_public_links=["https://example.com/post1"],
            learning_in_public_score=1,
            total_score=1,
        )
        first_answer = AnswerData(
            submission=submission,
            question=question1,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(first_answer)
        second_answer = AnswerData(
            submission=submission,
            question=question2,
            answer_text="1",
            is_correct=False,
        )
        self.create_answer(second_answer)
        return HomeworkSubmissionEditFixture(
            submission=submission,
            question1=question1,
            question2=question2,
        )

    def post_homework_submission_answer_edit(self, fixture):
        self.login_admin()
        data = {
            f"answer_{fixture.question1.id}": "4",
            f"answer_{fixture.question2.id}": "2",
            "learning_in_public_links": (
                "https://example.com/post1\n"
                "https://example.com/post2"
            ),
        }
        edit_url = self.homework_submission_edit_url(fixture.submission)
        return self.client.post(edit_url, data)

    def homework_submission_edit_response(self, submission):
        self.login_admin()
        url = self.homework_submission_edit_url(submission)
        response = self.client.get(url)
        return response

    def assert_homework_submission_edit_page(self, response, fixture):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Homework Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, fixture.question1.text)
        self.assertContains(response, fixture.question2.text)
        self.assertContains(response, 'value="3"')
        self.assertContains(response, "Manage enrollment")
        enrollment_url = reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": fixture.enrollment.id,
            },
        )
        self.assertContains(response, enrollment_url)

    def assert_homework_submission_scores(self, expectation):
        self.assertEqual(
            expectation.submission.questions_score,
            expectation.questions_score,
        )
        self.assertEqual(
            expectation.submission.learning_in_public_score,
            expectation.learning_in_public_score,
        )
        self.assertEqual(
            expectation.submission.total_score,
            expectation.total_score,
        )

    def assert_learning_in_public_links(self, submission, expected_links):
        self.assertEqual(
            len(submission.learning_in_public_links),
            len(expected_links),
        )
        for expected_link in expected_links:
            self.assertIn(expected_link, submission.learning_in_public_links)

    def cadmin_homework_submissions_url(self):
        return reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def homework_action_url(self, name):
        return reverse(
            name,
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

    def post_homework_action_to_submissions(self, action_name):
        next_url = self.cadmin_homework_submissions_url()
        data = {"next": next_url}
        action_url = self.homework_action_url(action_name)
        return self.client.post(action_url, data)

    def cadmin_course_url(self):
        return reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )

    def cadmin_course_response(self):
        self.login_admin()
        course_url = self.cadmin_course_url()
        return self.client.get(course_url)

    def assert_homework_submission_actions(self, response):
        homework_url = self.homework_url()
        self.assertContains(response, homework_url)
        self.assertContains(
            response,
            f"/admin/courses/homework/{self.homework.id}/change/",
        )
        set_correct_answers_url = self.homework_action_url(
            "cadmin_homework_set_correct_answers"
        )
        self.assertContains(
            response,
            set_correct_answers_url,
        )
        clear_correct_answers_url = self.homework_action_url(
            "cadmin_homework_clear_correct_answers"
        )
        self.assertContains(
            response,
            clear_correct_answers_url,
        )
        score_url = self.homework_action_url("cadmin_homework_score")
        self.assertContains(
            response,
            score_url,
        )
        self.assertContains(response, "Select most frequent answer")
        self.assertContains(response, "Clear correct answers")
        self.assertContains(response, "Score submissions")

    def homework_url(self):
        return reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
