import json
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


logger = logging.getLogger(__name__)

credentials = dict(username="testuser", password="12345")


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
            is_scored=False,
            slug="test-homework",
        )

        self.question1 = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="Paris,London,Berlin",
            correct_answer="Paris",
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
            possible_answers="2,3,4,5",
            correct_answer="2,3,5",
        )
        self.question3.save()

        self.question4 = Question.objects.create(
            homework=self.homework,
            text="How many continents are there on Earth?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="5,6,7",
            correct_answer="7",
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
            possible_answers="Blue,White,Red,Green",
            correct_answer="Blue,White,Red",
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
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, "homework/homework_detail.html"
        )

        context = response.context

        self.assertEquals(context["course"], self.course)
        self.assertEquals(context["homework"], self.homework)
        self.assertFalse(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEquals(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEquals(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False},
            {"value": "London", "is_selected": False},
            {"value": "Berlin", "is_selected": False},
        ]
        self.assertEquals(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEquals(question2, self.question2)
        self.assertEquals(answer2["text"], "")

        question3, answer3 = question_answers[2]
        self.assertEquals(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": False},
            {"value": "3", "is_selected": False},
            {"value": "4", "is_selected": False},
            {"value": "5", "is_selected": False},
        ]
        self.assertEquals(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEquals(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": False},
            {"value": "6", "is_selected": False},
            {"value": "7", "is_selected": False},
        ]
        self.assertEquals(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEquals(question5, self.question5)
        self.assertEquals(answer5["text"], "")

        question6, answer6 = question_answers[5]
        self.assertEquals(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": False},
            {"value": "White", "is_selected": False},
            {"value": "Red", "is_selected": False},
            {"value": "Green", "is_selected": False},
        ]
        self.assertEquals(answer6["options"], expected_options6)

    def test_homework_detail_authenticated_no_submission(self):
        self.client.login(**credentials)

        url = reverse(
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, "homework/homework_detail.html"
        )

        context = response.context

        self.assertEquals(context["course"], self.course)
        self.assertEquals(context["homework"], self.homework)
        self.assertTrue(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEquals(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEquals(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False},
            {"value": "London", "is_selected": False},
            {"value": "Berlin", "is_selected": False},
        ]
        self.assertEquals(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEquals(question2, self.question2)
        self.assertEquals(answer2["text"], "")

        question3, answer3 = question_answers[2]
        self.assertEquals(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": False},
            {"value": "3", "is_selected": False},
            {"value": "4", "is_selected": False},
            {"value": "5", "is_selected": False},
        ]
        self.assertEquals(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEquals(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": False},
            {"value": "6", "is_selected": False},
            {"value": "7", "is_selected": False},
        ]
        self.assertEquals(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEquals(question5, self.question5)
        self.assertEquals(answer5["text"], "")

        question6, answer6 = question_answers[5]
        self.assertEquals(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": False},
            {"value": "White", "is_selected": False},
            {"value": "Red", "is_selected": False},
            {"value": "Green", "is_selected": False},
        ]
        self.assertEquals(answer6["options"], expected_options6)

    def test_homework_detail_authenticated_with_submission(self):
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
            student=self.user,
            question=self.question1,
            answer_text="Berlin",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question3,
            answer_text="2,3",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question4,
            answer_text="5",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question6,
            answer_text="Blue,White,Red",
        )  # correct
        answer6.save()

        self.client.login(**credentials)

        url = reverse(
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.get(url)

        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, "homework/homework_detail.html"
        )

        context = response.context

        self.assertEquals(context["course"], self.course)
        self.assertEquals(context["homework"], self.homework)
        self.assertEquals(context["submission"], self.submission)
        self.assertTrue(context["is_authenticated"])

        question_answers = context["question_answers"]
        self.assertEquals(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEquals(question1, self.question1)
        expected_options1 = [
            {"value": "Paris", "is_selected": False},
            {"value": "London", "is_selected": False},
            {"value": "Berlin", "is_selected": True},
        ]
        self.assertEquals(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEquals(question2, self.question2)
        self.assertEquals(answer2["text"], "Some text")

        question3, answer3 = question_answers[2]
        self.assertEquals(question3, self.question3)
        expected_options3 = [
            {"value": "2", "is_selected": True},
            {"value": "3", "is_selected": True},
            {"value": "4", "is_selected": False},
            {"value": "5", "is_selected": False},
        ]
        self.assertEquals(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEquals(question4, self.question4)
        expected_options4 = [
            {"value": "5", "is_selected": True},
            {"value": "6", "is_selected": False},
            {"value": "7", "is_selected": False},
        ]
        self.assertEquals(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEquals(question5, self.question5)
        self.assertEquals(answer5["text"], "3.141516")

        question6, answer6 = question_answers[5]
        self.assertEquals(question6, self.question6)
        expected_options6 = [
            {"value": "Blue", "is_selected": True},
            {"value": "White", "is_selected": True},
            {"value": "Red", "is_selected": True},
            {"value": "Green", "is_selected": False},
        ]
        self.assertEquals(answer6["options"], expected_options6)

    def test_homework_detail_with_scored_homework(self):
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
            student=self.user,
            question=self.question1,
            answer_text="Berlin",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question3,
            answer_text="2,3,4",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question4,
            answer_text="5",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question6,
            answer_text="Blue,White,Red",
        )  # correct
        answer6.save()

        # update homework's due date to be in the past
        self.homework.due_date = timezone.now() - timezone.timedelta(
            days=1
        )
        self.homework.save()

        status, _ = score_homework_submissions(self.homework.id)
        self.assertEquals(status, HomeworkScoringStatus.OK)

        # make sure we have the latest version of the homework
        self.homework = Homework.objects.get(id=self.homework.id)
        self.assertTrue(self.homework.is_scored)

        self.client.login(**credentials)

        url = reverse(
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.get(url)

        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(
            response, "homework/homework_detail.html"
        )

        context = response.context

        self.assertEquals(context["course"], self.course)
        self.assertEquals(context["homework"], self.homework)
        self.assertEquals(context["submission"], self.submission)
        self.assertTrue(context["is_authenticated"])

        self.assertTrue(context["homework"].is_scored)

        question_answers = context["question_answers"]
        self.assertEquals(len(question_answers), 6)

        question1, answer1 = question_answers[0]
        self.assertEquals(question1, self.question1)
        expected_options1 = [
            {
                "value": "Paris",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "London",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
            },
            {
                "value": "Berlin",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
            },
        ]
        self.assertEquals(answer1["options"], expected_options1)

        question2, answer2 = question_answers[1]
        self.assertEquals(question2, self.question2)
        self.assertEquals(answer2["text"], "Some text")
        self.assertEquals(
            answer2["correctly_selected_class"],
            "option-answer-correct",
        )

        question3, answer3 = question_answers[2]
        self.assertEquals(question3, self.question3)
        expected_options3 = [
            {
                "value": "2",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "3",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "4",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
            },
            {
                "value": "5",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
            },
        ]
        self.assertEquals(answer3["options"], expected_options3)

        question4, answer4 = question_answers[3]
        self.assertEquals(question4, self.question4)
        expected_options4 = [
            {
                "value": "5",
                "is_selected": True,
                "correctly_selected_class": "option-answer-incorrect",
            },
            {
                "value": "6",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
            },
            {
                "value": "7",
                "is_selected": False,
                "correctly_selected_class": "option-answer-correct",
            },
        ]
        self.assertEquals(answer4["options"], expected_options4)

        question5, answer5 = question_answers[4]
        self.assertEquals(question5, self.question5)
        self.assertEquals(answer5["text"], "3.141516")
        self.assertEquals(
            answer5["correctly_selected_class"],
            "option-answer-correct",
        )

        question6, answer6 = question_answers[5]
        self.assertEquals(question6, self.question6)
        expected_options6 = [
            {
                "value": "Blue",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "White",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "Red",
                "is_selected": True,
                "correctly_selected_class": "option-answer-correct",
            },
            {
                "value": "Green",
                "is_selected": False,
                "correctly_selected_class": "option-answer-none",
            },
        ]
        self.assertEquals(answer6["options"], expected_options6)

    def test_homework_detail_submission_post_no_submissions(self):
        # enrollment doesn't exist yet
        enrollment = Enrollment.objects.filter(
            student=self.user, course=self.course
        )
        self.assertFalse(enrollment.exists())

        # submission doesn't exist yet
        submission = Submission.objects.filter(
            student=self.user, homework=self.homework
        )
        self.assertFalse(submission.exists())

        post_data = {
            f"answer_{self.question1.id}": ["Berlin"],
            f"answer_{self.question2.id}": ["Some text"],
            f"answer_{self.question3.id}": ["2", "3"],
            f"answer_{self.question4.id}": ["5"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["Blue", "White", "Red"],
        }

        url = reverse(
            "homework_detail",
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

        self.assertEquals(response.status_code, 302)

        # check that redict url is correct
        redirect_url = reverse(
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        self.assertEquals(response.url, redirect_url)

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
        answers = Answer.objects.filter(
            student=self.user, submission=submission
        )

        self.assertEquals(len(answers), 6)

        answer1 = answers.get(question=self.question1)
        self.assertEquals(answer1.answer_text, "Berlin")

        answer2 = answers.get(question=self.question2)
        self.assertEquals(answer2.answer_text, "Some text")

        answer3 = answers.get(question=self.question3)
        self.assertEquals(answer3.answer_text, "2,3")

        answer4 = answers.get(question=self.question4)
        self.assertEquals(answer4.answer_text, "5")

        answer5 = answers.get(question=self.question5)
        self.assertEquals(answer5.answer_text, "3.141516")

        answer6 = answers.get(question=self.question6)
        self.assertEquals(answer6.answer_text, "Blue,White,Red")

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
            student=self.user,
            question=self.question1,
            answer_text="Berlin",
        )  # incorrect
        answer1.save()

        answer2 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question2,
            answer_text="Some text",
        )  # any answer is correct
        answer2.save()

        answer3 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question3,
            answer_text="2,3,4",
        )  # partially correct
        answer3.save()

        answer4 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question4,
            answer_text="5",
        )  # incorrect
        answer4.save()

        answer5 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question5,
            answer_text="3.141516",
        )  # correct
        answer5.save()

        answer6 = Answer.objects.create(
            submission=self.submission,
            student=self.user,
            question=self.question6,
            answer_text="Blue,White,Red",
        )  # correct
        answer6.save()

        self.client.login(**credentials)

        post_data = {
            f"answer_{self.question1.id}": ["Paris"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["2", "3", "5"],
            f"answer_{self.question4.id}": ["7"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["Blue", "White"],
        }

        url = reverse(
            "homework_detail",
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

        self.assertEquals(response.status_code, 302)

        # check that redict url is correct
        redirect_url = reverse(
            "homework_detail",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        self.assertEquals(response.url, redirect_url)

        # submitted_at is updated to "now"
        submission = Submission.objects.get(id=self.submission.id)
        self.assertEquals(submission.submitted_at, update_time_now)

        # check updated answers
        answers = Answer.objects.filter(
            student=self.user, submission=submission
        )

        self.assertEquals(len(answers), 6)

        answer1 = answers.get(question=self.question1)
        self.assertEquals(answer1.answer_text, "Paris")

        answer2 = answers.get(question=self.question2)
        self.assertEquals(answer2.answer_text, "Some other text")

        answer3 = answers.get(question=self.question3)
        self.assertEquals(answer3.answer_text, "2,3,5")

        answer4 = answers.get(question=self.question4)
        self.assertEquals(answer4.answer_text, "7")

        answer5 = answers.get(question=self.question5)
        self.assertEquals(answer5.answer_text, "3.141516")

        answer6 = answers.get(question=self.question6)
        self.assertEquals(answer6.answer_text, "Blue,White")

    def test_submit_homework_with_all_fields(self):
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
            f"answer_{self.question1.id}": ["Paris"],
            f"answer_{self.question2.id}": ["Some other text"],
            f"answer_{self.question3.id}": ["2", "3", "5"],
            f"answer_{self.question4.id}": ["7"],
            f"answer_{self.question5.id}": ["3.141516"],
            f"answer_{self.question6.id}": ["Blue", "White"],

            "homework_url": "http://example.com/homework",
            "learning_in_public_links[]": [
                "http://example.com/link1",
                "http://example.com/link2",
            ],
            "time_spent_lectures": "5",
            "time_spent_homework": "3",
            "problems_comments": "Some problems and comments",
            "faq_contribution": "FAQ contributions",
        }

        url = reverse(
            "homework_detail",
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
        self.assertEqual(
            json.loads(submission.learning_in_public_links),
            post_data["learning_in_public_links[]"],
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
