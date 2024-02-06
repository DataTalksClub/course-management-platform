from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
)

from .util import join_possible_answers

credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345"
)


class CourseDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course-2"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )

        # Create homeworks
        self.homework1 = Homework.objects.create(
            slug="scored-homework", 
            course=self.course,
            title="Scored Homework",
            description="This homework is already scored.",
            due_date=timezone.now() - timezone.timedelta(days=1),
            is_scored=True,
        )

        self.homework2 = Homework.objects.create(
            slug="submitted-homework",
            course=self.course,
            title="Submitted Homework",
            description="Homework with submitted answers.",
            due_date=timezone.now() + timezone.timedelta(days=7),
            is_scored=False,
        )

        self.homework3 = Homework.objects.create(
            slug="unscored-homework",
            course=self.course,
            title="Homework Without Submissions",
            description="Homework without any submissions yet.",
            due_date=timezone.now() + timezone.timedelta(days=14),
            is_scored=False,
        )

        self.homeworks = [self.homework1, self.homework2, self.homework3]

        for hw in self.homeworks:
            for i in range(1, 4):
                Question.objects.create(
                    homework=hw,
                    text=f"Question {i} of {hw.title}",
                    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                    possible_answers=join_possible_answers(['A', 'B', 'C', 'D']),
                    correct_answer="A",
                )

        # Create submissions for the first two homeworks
        self.submission1 = Submission.objects.create(
            homework=self.homework1,
            enrollment=self.enrollment,
            student=self.user,
            total_score=80,  # Assuming this is a scored submission
        )

        self.submission2 = Submission.objects.create(
            homework=self.homework2,
            enrollment=self.enrollment,
            student=self.user,
            total_score=0,  # Assuming this is an unscored submission
        )

    def test_course_detail_unauthenticated_user(self):
        # Test the view for an unauthenticated user
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertTemplateUsed(response, 'courses/course.html')
        self.assertEqual(response.status_code, 200)
        
        context = response.context

        self.assertFalse(context["is_authenticated"])
        self.assertEqual(context['course'], self.course)
        self.assertEqual(len(context['homeworks']), 3)

        # Check the properties of each homework in the context
        for hw in context['homeworks']:
            self.assertIn(hw.title, [h.title for h in self.homeworks])
            self.assertFalse(hw.submitted)
            self.assertIsNone(hw.score)
            self.assertFalse(hasattr(hw, 'submitted_at'))


    def test_course_detail_authenticated_user(self):
        # Test the view for an authenticated user
        self.client.login(**credentials)

        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        
        context = response.context

        self.assertTrue(context["is_authenticated"])
        self.assertEqual(context['course'], self.course)
        self.assertEqual(len(context['homeworks']), 3)

        homeworks = {h.slug: h for h in response.context['homeworks']}

        scored_homework = homeworks['scored-homework']
        self.assertTrue(scored_homework.submitted)
        self.assertFalse(hasattr(scored_homework, 'submitted_at'))
        self.assertEquals(scored_homework.is_scored, True)
        self.assertEquals(scored_homework.score, 80)
        self.assertEquals(scored_homework.days_until_due, 0)

        submitted_homework = homeworks['submitted-homework']
        self.assertTrue(submitted_homework.submitted)
        self.assertEquals(submitted_homework.submitted_at, self.submission2.submitted_at)
        self.assertEquals(submitted_homework.is_scored, False)
        self.assertEquals(submitted_homework.score, None)
        self.assertEquals(submitted_homework.days_until_due, 7)

        unscored_homework = homeworks['unscored-homework']
        self.assertFalse(unscored_homework.submitted)
        self.assertFalse(hasattr(unscored_homework, 'submitted_at'))
        self.assertEquals(unscored_homework.is_scored, False)
        self.assertEquals(unscored_homework.score, None)
        self.assertEquals(unscored_homework.days_until_due, 14)
        self.assertEquals(unscored_homework.submissions, [])

        self.assertEquals(context['total_score'], 80)
