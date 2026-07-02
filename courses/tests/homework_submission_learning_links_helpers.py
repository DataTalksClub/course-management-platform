from django.utils import timezone

from courses.models import Homework, Submission


def reused_learning_link_post_data():
    return {
        "learning_in_public_links[]": ["https://example.com/post"]
    }


def create_previous_homework_submission_with_learning_link(test_case):
    due_date = timezone.now()
    previous_homework = Homework.objects.create(
        course=test_case.course,
        slug="hw0",
        title="Homework 0",
        due_date=due_date,
    )
    Submission.objects.create(
        homework=previous_homework,
        student=test_case.user,
        enrollment=test_case.enrollment,
        learning_in_public_links=["https://example.com/post"],
    )


def assert_reused_learning_link_rejected(test_case, response):
    test_case.assertEqual(response.status_code, 200)
    test_case.assertContains(
        response,
        "Learning in public links were already used",
    )


def assert_current_homework_not_submitted(test_case):
    submission_exists = Submission.objects.filter(
        student=test_case.user,
        homework=test_case.homework,
    ).exists()
    test_case.assertFalse(submission_exists)
