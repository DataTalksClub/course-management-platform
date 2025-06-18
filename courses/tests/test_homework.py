import logging

from datetime import datetime
from unittest import mock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    HomeworkState,
    Question,
    Submission,
    Answer,
    Enrollment,
    QuestionTypes,
    AnswerTypes,
)

from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from .util import join_possible_answers

logger = logging.getLogger(__name__)

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


class HomeworkDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.homework = Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
            # is_scored=False,
            slug="test-homework",
        )

        self.question1 = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(
                ["Paris", "London", "Berlin"]
            ),
            correct_answer="1",
        )
        self.question1.save()

        self.question2 = Question.objects.create(
            homework=self.homework,
            text="Explain the theory of relativity.",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.ANY.value,
        )
        self.question2.save()

        self.question3 = Question.objects.create(
            homework=self.homework,
            text="Select prime numbers.",
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers=join_possible_answers(
                ["2", "3", "4", "5"]
            ),
            correct_answer="1,2,4",
        )
        self.question3.save()

        self.question4 = Question.objects.create(
            homework=self.homework,
            text="How many continents are there on Earth?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(["5", "6", "7"]),
            correct_answer="3",
        )
        self.question4.save()

        self.question5 = Question.objects.create(
            homework=self.homework,
            text="What is the value of Pi (up to 2 decimal places)?",
            question_type=QuestionTypes.FREE_FORM.value,
            answer_type=AnswerTypes.FLOAT.value,
            correct_answer="3.14",
        )
        self.question5.save()

        self.question6 = Question.objects.create(
            homework=self.homework,
            text="Select the colors in the French flag.",
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers=join_possible_answers(
                ["Blue", "White", "Red", "Green"]
            ),
            correct_answer="1,2,3",
        )
        self.question6.save()

        self.quesions = [
            self.question1,
            self.question2,
            self.question3,
            self.question4,
            self.question5,
            self.question6,
        ]

    def test_homework_detail_unauthenticated(self):
        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = response.context

        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)
        self.assertFalse(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEqual(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEqual(question2, self.question2)
        self.assertEqual(answer2["text"], "")

        question3, answer3 = question_answers[2]
        self.assertEqual(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": False, "index": 1},
            {"value": "3", "is_selected": False, "index": 2},
            {"value": "4", "is_selected": False, "index": 3},
            {"value": "5", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEqual(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": False, "index": 1},
            {"value": "6", "is_selected": False, "index": 2},
            {"value": "7", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEqual(question5, self.question5)
        self.assertEqual(answer5["text"], "")

        question6, answer6 = question_answers[5]
        self.assertEqual(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": False, "index": 1},
            {"value": "White", "is_selected": False, "index": 2},
            {"value": "Red", "is_selected": False, "index": 3},
            {"value": "Green", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer6["options"], expected_options6)

    def test_homework_detail_authenticated_no_submission(self):
        self.client.login(**credentials)

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = response.context

        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)
        self.assertTrue(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEqual(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEqual(question2, self.question2)
        self.assertEqual(answer2["text"], "")

        question3, answer3 = question_answers[2]
        self.assertEqual(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": False, "index": 1},
            {"value": "3", "is_selected": False, "index": 2},
            {"value": "4", "is_selected": False, "index": 3},
            {"value": "5", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEqual(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": False, "index": 1},
            {"value": "6", "is_selected": False, "index": 2},
            {"value": "7", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEqual(question5, self.question5)
        self.assertEqual(answer5["text"], "")

        question6, answer6 = question_answers[5]
        self.assertEqual(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": False, "index": 1},
            {"value": "White", "is_selected": False, "index": 2},
            {"value": "Red", "is_selected": False, "index": 3},
            {"value": "Green", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer6["options"], expected_options6)

    def test_homework_detail_authenticated_with_submission(self):
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
        )

        answer1 = Answer.objects.create(
            submission=self.submission,
            question=self.question1,
            answer_text="3",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            question=self.question3,
            answer_text="1,2",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            question=self.question4,
            answer_text="1",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            question=self.question6,
            answer_text="1,2,3",
        )  # correct
        answer6.save()

        self.client.login(**credentials)

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        logger.info(f"url={url}")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = response.context

        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)
        self.assertEqual(context["submission"], self.submission)
        self.assertTrue(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEqual(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": True, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEqual(question2, self.question2)
        self.assertEqual(answer2["text"], "Some text")

        question3, answer3 = question_answers[2]
        self.assertEqual(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": True, "index": 1},
            {"value": "3", "is_selected": True, "index": 2},
            {"value": "4", "is_selected": False, "index": 3},
            {"value": "5", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEqual(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": True, "index": 1},
            {"value": "6", "is_selected": False, "index": 2},
            {"value": "7", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEqual(question5, self.question5)
        self.assertEqual(answer5["text"], "3.141516")

        question6, answer6 = question_answers[5]
        self.assertEqual(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": True, "index": 1},
            {"value": "White", "is_selected": True, "index": 2},
            {"value": "Red", "is_selected": True, "index": 3},
            {"value": "Green", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer6["options"], expected_options6)

    def test_homework_detail_with_scored_homework(self):
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )
        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
        )

        answer1 = Answer.objects.create(
            submission=self.submission,
            question=self.question1,
            answer_text="3",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            question=self.question3,
            answer_text="1,2,3",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            question=self.question4,
            answer_text="1",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            question=self.question6,
            answer_text="1,2,3",
        )  # correct
        answer6.save()

        # update homework's due date to be in the past
        self.homework.due_date = timezone.now() - timezone.timedelta(
            days=1
        )
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)
        self.assertEqual(status, HomeworkScoringStatus.OK)

        # make sure we have the latest version of the homework
        self.homework = Homework.objects.get(id=self.homework.id)
        self.assertEqual(
            self.homework.state, HomeworkState.SCORED.value
        )
        self.assertTrue(self.homework.is_scored())

        self.client.login(**credentials)

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homework/homework.html")

        context = response.context

        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)
        self.assertEqual(context["submission"], self.submission)
        self.assertTrue(context["is_authenticated"])

        self.assertTrue(context["homework"].is_scored)

        question_answers = context["question_answers"]
        self.assertEqual(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {
                "value": "Paris",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
                "index": 1,
            },
            {
                "value": "London",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
                "index": 2,
            },
            {
                "value": "Berlin",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
                "index": 3,
            },
        ]
        self.assertEqual(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEqual(question2, self.question2)
        self.assertEqual(answer2["text"], "Some text")
        self.assertEqual(
            answer2["correctly_selected_class"],
            "option-answer-correct",
        )

        question3, answer3 = question_answers[2]
        self.assertEqual(question3, self.question3)
        expected_options3 = [
            {
                "value": "2",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
                "index": 1,
            },
            {
                "value": "3",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
                "index": 2,
            },
            {
                "value": "4",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
                "index": 3,
            },
            {
                "value": "5",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
                "index": 4,
            },
        ]
        self.assertEqual(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEqual(question4, self.question4)
        expected_options4 = [
            {
                "value": "5",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
                "index": 1,
            },
            {
                "value": "6",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
                "index": 2,
            },
            {
                "value": "7",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
                "index": 3,
            },
        ]
        self.assertEqual(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEqual(question5, self.question5)
        self.assertEqual(answer5["text"], "3.141516")
        self.assertEqual(
            answer5["correctly_selected_class"],
            "option-answer-correct",
        )

        question6, answer6 = question_answers[5]
        self.assertEqual(question6, self.question6)
        expected_options6 = [
            {
                "value": "Blue",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
                "index": 1,
            },
            {
                "value": "White",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
                "index": 2,
            },
            {
                "value": "Red",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
                "index": 3,
            },
            {
                "value": "Green",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
                "index": 4,
            },
        ]
        self.assertEqual(answer6["options"], expected_options6)

    def test_homework_detail_submission_post_no_submissions(self):
        # enrollment doesn't exist yet
        enrollment = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
        )
        self.assertFalse(enrollment.exists())

        # submission doesn't exist yet
        submission = Submission.objects.filter(
            student=self.user, homework=self.homework
        )
        self.assertFalse(submission.exists())

        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some text"],
            f"answer_{self.question3.id}": ["1", "2"],
            f"answer_{self.question4.id}": ["1"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2", "3"],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        response = self.client.post(
            url,
            post_data,
        )

        self.assertEqual(response.status_code, 302)

        # check that redict url is correct
        redirect_url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        self.assertEqual(response.url, redirect_url)

        # now enrollment exists
        enrollment = Enrollment.objects.filter(
            student=self.user, course=self.course
        )
        self.assertTrue(enrollment.exists())

        # now submission exists
        submissions = Submission.objects.filter(
            student=self.user, homework=self.homework
        )
        self.assertTrue(submissions.exists())

        submission = submissions.first()

        # now answers exist too
        answers = Answer.objects.filter(submission=submission)

        self.assertEqual(len(answers), 6)

        answer1 = answers.get(question=self.question1)
        self.assertEqual(answer1.answer_text, "1")

        answer2 = answers.get(question=self.question2)
        self.assertEqual(answer2.answer_text, "Some text")

        answer3 = answers.get(question=self.question3)
        self.assertEqual(answer3.answer_text, "1,2")

        answer4 = answers.get(question=self.question4)
        self.assertEqual(answer4.answer_text, "1")

        answer5 = answers.get(question=self.question5)
        self.assertEqual(answer5.answer_text, "3.141516")

        answer6 = answers.get(question=self.question6)
        self.assertEqual(answer6.answer_text, "1,2,3")

    @mock.patch("django.utils.timezone.now")
    def test_homework_detail_submission_post_with_submissions(
        self, mock_now
    ):
        update_time_now = timezone.make_aware(datetime(2020, 1, 1))
        mock_now.return_value = update_time_now

        self.enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
        )

        answer1 = Answer.objects.create(
            submission=self.submission,
            question=self.question1,
            answer_text="1",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            question=self.question3,
            answer_text="1,2,3",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            question=self.question4,
            answer_text="1",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            question=self.question6,
            answer_text="1,2,3",
        )  # correct
        answer6.save()

        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        response = self.client.post(
            url,
            post_data,
        )

        self.assertEqual(response.status_code, 302)

        # check that redict url is correct
        redirect_url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        self.assertEqual(response.url, redirect_url)

        # submitted_at is updated to "now"
        submission = Submission.objects.get(id=self.submission.id)
        self.assertEqual(submission.submitted_at, update_time_now)

        # check updated answers
        answers = Answer.objects.filter(submission=submission)

        self.assertEqual(len(answers), 6)

        answer1 = answers.get(question=self.question1)
        self.assertEqual(answer1.answer_text, "1")

        answer2 = answers.get(question=self.question2)
        self.assertEqual(answer2.answer_text, "Some other text")

        answer3 = answers.get(question=self.question3)
        self.assertEqual(answer3.answer_text, "1,2,4")

        answer4 = answers.get(question=self.question4)
        self.assertEqual(answer4.answer_text, "3")

        answer5 = answers.get(question=self.question5)
        self.assertEqual(answer5.answer_text, "3.141516")

        answer6 = answers.get(question=self.question6)
        self.assertEqual(answer6.answer_text, "1,2")

    def test_submit_homework_with_all_fields(self):
        self.course.homework_problems_comments_field = True
        self.course.save()

        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 7
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.faq_contribution_field = True
        self.homework.save()

        self.client.login(**credentials)

        # the submission data
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
            "homework_url": "https://httpbin.org/status/200",
            "learning_in_public_links[]": [
                "https://httpbin.org/status/200",
                "https://github.com/DataTalksClub",
                "",
            ],
            "time_spent_lectures": "5",
            "time_spent_homework": "3",
            "problems_comments": "Some problems and comments",
            "faq_contribution": "FAQ contributions",
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        self.client.post(url, post_data)

        # Retrieve the updated submission object
        submission = Submission.objects.get(
            homework=self.homework, student=self.user
        )

        # Assertions to verify that the data is saved correctly
        self.assertEqual(
            submission.homework_link, post_data["homework_url"]
        )

        expected_learning_in_public_links = [
            "https://httpbin.org/status/200",
            "https://github.com/DataTalksClub",
        ]
        self.assertEqual(
            submission.learning_in_public_links,
            expected_learning_in_public_links,
        )

        self.assertEqual(
            submission.time_spent_lectures,
            float(post_data["time_spent_lectures"]),
        )
        self.assertEqual(
            submission.time_spent_homework,
            float(post_data["time_spent_homework"]),
        )
        self.assertEqual(
            submission.problems_comments,
            post_data["problems_comments"],
        )
        self.assertEqual(
            submission.faq_contribution,
            post_data["faq_contribution"],
        )

    def test_submit_homework_with_all_fields_optional_empty(self):
        self.homework.homework_url_field = True
        self.homework.learning_in_public_cap = 7
        self.homework.time_spent_lectures_field = True
        self.homework.time_spent_homework_field = True
        self.homework.problems_comments_field = True
        self.homework.faq_contribution_field = True

        self.homework.save()

        self.client.login(**credentials)

        # the submission data
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
            "homework_url": "https://httpbin.org/status/200",
            "learning_in_public_links[]": [""],
            "time_spent_lectures": "",
            "time_spent_homework": "",
            "problems_comments": "",
            "faq_contribution": "",
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        self.client.post(url, post_data)

        # Retrieve the updated submission object
        submission = Submission.objects.get(
            homework=self.homework, student=self.user
        )

        # Assertions to verify that the data is saved correctly
        self.assertEqual(
            submission.homework_link, post_data["homework_url"]
        )

        self.assertEqual(submission.learning_in_public_links, [])

        self.assertEqual(submission.time_spent_lectures, None)
        self.assertEqual(submission.time_spent_homework, None)
        self.assertEqual(submission.problems_comments, "")
        self.assertEqual(submission.faq_contribution, "")

    def test_submit_homework_learning_in_public_empty_and_duplicates(
        self,
    ):
        self.homework.learning_in_public_cap = 7
        self.homework.save()

        self.client.login(**credentials)

        # the submission data
        post_data = {
            f"answer_{self.question1.id}": ["1"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["1", "2", "4"],
            f"answer_{self.question4.id}": ["3"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1", "2"],
            "learning_in_public_links[]": [
                "https://httpbin.org/status/200",
                "https://httpbin.org/status/200",
                "https://github.com/DataTalksClub",
            ],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        self.client.post(url, post_data)

        # Retrieve the updated submission object
        submission = Submission.objects.get(
            homework=self.homework, student=self.user
        )

        expected_learning_in_public_links = [
            "https://httpbin.org/status/200",
            "https://github.com/DataTalksClub",
        ]
        self.assertEqual(
            submission.learning_in_public_links,
            expected_learning_in_public_links,
        )

    def test_submit_homework_submission_artifacts(self):
        post_data = {
            f"answer_{self.question1.id}": ["1\r\n"],
            f"answer_{self.question2.id}": ["Some text"],
            f"answer_{self.question3.id}": ["1\r\n", "2"],
            f"answer_{self.question4.id}": ["1"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1\r\n", "2\r\n", "3"],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.login(**credentials)

        self.client.post(
            url,
            post_data,
        )

        submission = Submission.objects.filter(
            student=self.user, homework=self.homework
        ).first()

        answers = Answer.objects.filter(submission=submission)

        self.assertEqual(len(answers), 6)

        answer1 = answers.get(question=self.question1)
        self.assertEqual(answer1.answer_text, "1")

        answer2 = answers.get(question=self.question2)
        self.assertEqual(answer2.answer_text, "Some text")

        answer3 = answers.get(question=self.question3)
        self.assertEqual(answer3.answer_text, "1,2")

        answer4 = answers.get(question=self.question4)
        self.assertEqual(answer4.answer_text, "1")

        answer5 = answers.get(question=self.question5)
        self.assertEqual(answer5.answer_text, "3.141516")

        answer6 = answers.get(question=self.question6)
        self.assertEqual(answer6.answer_text, "1,2,3")

    def test_submit_homework_submission_artifacts_dispayed_correctly(
        self,
    ):
        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["3\r\n"],
            f"answer_{self.question2.id}": ["Some text"],
            f"answer_{self.question3.id}": ["1\r\n", "2"],
            f"answer_{self.question4.id}": ["1"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["1\r\n", "2\r\n", "3"],
        }

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.post(url, post_data)

        # now the results are saved, let's get them
        response = self.client.get(url)
        context = response.context

        question_answers = context["question_answers"]
        self.assertEqual(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": True, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEqual(question2, self.question2)
        self.assertEqual(answer2["text"], "Some text")

        question3, answer3 = question_answers[2]
        self.assertEqual(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": True, "index": 1},
            {"value": "3", "is_selected": True, "index": 2},
            {"value": "4", "is_selected": False, "index": 3},
            {"value": "5", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEqual(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": True, "index": 1},
            {"value": "6", "is_selected": False, "index": 2},
            {"value": "7", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEqual(question5, self.question5)
        self.assertEqual(answer5["text"], "3.141516")

        question6, answer6 = question_answers[5]
        self.assertEqual(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": True, "index": 1},
            {"value": "White", "is_selected": True, "index": 2},
            {"value": "Red", "is_selected": True, "index": 3},
            {"value": "Green", "is_selected": False, "index": 4},
        ]
        self.assertEqual(answer6["options"], expected_options6)

    def test_submit_homework_submission_artifacts_in_possible_answers(
        self,
    ):
        self.question1.possible_answers = join_possible_answers(
            ["Paris\r", "London\r", "Berlin"]
        )
        self.question1.save()

        self.client.login(**credentials)

        post_data = {f"answer_{self.question1.id}": ["1\r\n"]}

        url = reverse(
            "homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        self.client.post(url, post_data)

        response = self.client.get(url)
        context = response.context

        question_answers = context["question_answers"]

        question1, answer1 = question_answers[0]
        self.assertEqual(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": True, "index": 1},
            {"value": "London", "is_selected": False, "index": 2},
            {"value": "Berlin", "is_selected": False, "index": 3},
        ]
        self.assertEqual(answer1["options"], expected_options1)
