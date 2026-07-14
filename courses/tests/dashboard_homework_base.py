from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
    Submission,
)


User = get_user_model()


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class DashboardHomeworkStatsTestBase(TestCase):
    def create_dashboard_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            first_homework_scored=True,
        )

    def create_dashboard_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.SCORED.value,
        )

    def create_dashboard_enrollments(self, count):
        for i in range(count):
            user = self.create_dashboard_stat_user(i)
            enrollment = self.create_dashboard_stat_enrollment(user)
            self.users.append(user)
            self.enrollments.append(enrollment)

    def create_dashboard_stat_user(self, index):
        user_creds = {
            "username": f"user{index}@test.com",
            "email": f"user{index}@test.com",
            "password": "12345",
        }
        return User.objects.create_user(**user_creds)

    def create_dashboard_stat_enrollment(self, user):
        return Enrollment.objects.create(
            student=user,
            course=self.course,
        )

    def create_homework_submission(self, user, enrollment, scores=None):
        if scores is None:
            scores = {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            }

        return Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            **scores,
        )

    def homework_submission_stats_data(self):
        return [
            {
                "time_spent_lectures": 1.0,
                "time_spent_homework": 2.0,
                "total_score": 80,
            },
            {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            },
            {
                "time_spent_lectures": 3.0,
                "time_spent_homework": 4.0,
                "total_score": 90,
            },
            {
                "time_spent_lectures": 4.0,
                "time_spent_homework": 5.0,
                "total_score": 95,
            },
            {
                "time_spent_lectures": 5.0,
                "time_spent_homework": 6.0,
                "total_score": 100,
            },
        ]

    def create_homework_stat_submissions(self):
        submission_stats = self.homework_submission_stats_data()
        for index, data in enumerate(submission_stats):
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                data,
            )

    def null_time_submission_stats_data(self):
        return [
            {
                "time_spent_lectures": 2.0,
                "time_spent_homework": 3.0,
                "total_score": 85,
            },
            {
                "time_spent_lectures": None,
                "time_spent_homework": 4.0,
                "total_score": 90,
            },
            {
                "time_spent_lectures": 3.0,
                "time_spent_homework": None,
                "total_score": 80,
            },
            {
                "time_spent_lectures": 4.0,
                "time_spent_homework": 5.0,
                "total_score": 95,
            },
        ]

    def create_null_time_submissions(self):
        submission_stats = self.null_time_submission_stats_data()
        for index, data in enumerate(submission_stats):
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                data,
            )

    def assert_homework_stat_summary(self, hw_stat):
        self.assertEqual(hw_stat["homework"], self.homework)
        self.assertEqual(hw_stat["submissions_count"], 5)
        self.assertEqual(hw_stat["completion_rate"], 100.0)
        self.assertEqual(hw_stat["time_lecture_median"], 3.0)
        self.assertEqual(hw_stat["time_homework_median"], 4.0)
        self.assertEqual(hw_stat["time_total_median"], 7.0)
        self.assertEqual(hw_stat["score_median"], 90)

    def assert_null_time_homework_stats(self, hw_stat):
        self.assertEqual(hw_stat["submissions_count"], 4)
        self.assertIsNotNone(hw_stat["time_lecture_median"])

    def create_formatted_time_submissions(self):
        scores = {
            "time_spent_lectures": 3.0,
            "time_spent_homework": 4.0,
            "total_score": 85,
        }
        self.create_homework_submission(
            self.users[0],
            self.enrollments[0],
            scores,
        )

        for index in range(1, 4):
            scores = {
                "time_spent_lectures": 3.0 + index,
                "time_spent_homework": 4.0 + index,
                "total_score": 85 + index,
            }
            self.create_homework_submission(
                self.users[index],
                self.enrollments[index],
                scores,
            )

    def assert_formatted_time_fields(self, hw_stat):
        self.assertIn("time_lecture_median_formatted", hw_stat)
        self.assertIn("time_homework_median_formatted", hw_stat)
        self.assertIn("time_total_median_formatted", hw_stat)

    def add_questions(self, homework, count):
        questions = []
        for i in range(count):
            question = Question(
                homework=homework,
                text=f"Q{i}",
                question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                scores_for_correct_answer=1,
            )
            questions.append(question)
        Question.objects.bulk_create(questions)

    def create_homework_for_difficulty(self, slug, title, days_until_due):
        homework = Homework.objects.create(
            course=self.course,
            slug=slug,
            title=title,
            due_date=timezone.now() + timedelta(days=days_until_due),
            state=HomeworkState.SCORED.value,
        )
        return homework

    def create_difficulty_submissions(self, harder_homework):
        for user, enrollment in zip(self.users, self.enrollments):
            Submission.objects.create(
                homework=self.homework,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0,
                time_spent_homework=3.0,
                questions_score=3,
                total_score=3,
            )
            Submission.objects.create(
                homework=harder_homework,
                student=user,
                enrollment=enrollment,
                time_spent_lectures=2.0,
                time_spent_homework=3.0,
                questions_score=5,
                total_score=12,
            )

    def assert_difficulty_ranking(self, response, harder_homework):
        difficulty_stats = response.context["homework_difficulty_stats"]
        self.assertEqual(difficulty_stats[0]["homework"], harder_homework)
        self.assertEqual(difficulty_stats[0]["difficulty_rank"], 1)
        self.assertEqual(difficulty_stats[0]["score_ratio_pct"], 50.0)
        self.assertEqual(difficulty_stats[0]["max_questions_score"], 10)
        self.assertEqual(difficulty_stats[1]["homework"], self.homework)
        self.assertEqual(difficulty_stats[1]["difficulty_rank"], 2)
        self.assertEqual(difficulty_stats[1]["score_ratio_pct"], 100.0)

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_dashboard_course()
        self.homework = self.create_dashboard_homework()
        self.users = []
        self.enrollments = []
        self.create_dashboard_enrollments(5)
