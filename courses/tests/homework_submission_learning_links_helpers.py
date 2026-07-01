from django.utils import timezone

from courses.models import Homework, Submission


class HomeworkSubmissionLearningLinksMixin:
    def reused_learning_link_post_data(self):
        return {
            "learning_in_public_links[]": ["https://example.com/post"]
        }

    def create_previous_homework_submission_with_learning_link(self):
        due_date = timezone.now()
        previous_homework = Homework.objects.create(
            course=self.course,
            slug="hw0",
            title="Homework 0",
            due_date=due_date,
        )
        Submission.objects.create(
            homework=previous_homework,
            student=self.user,
            enrollment=self.enrollment,
            learning_in_public_links=["https://example.com/post"],
        )

    def assert_reused_learning_link_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Learning in public links were already used",
        )

    def assert_current_homework_not_submitted(self):
        submission_exists = Submission.objects.filter(
            student=self.user,
            homework=self.homework,
        ).exists()
        self.assertFalse(submission_exists)
