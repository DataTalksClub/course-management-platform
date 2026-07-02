from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    Project,
    ProjectState,
    ProjectSubmission,
    Question,
    QuestionTypes,
    Submission,
    User,
)


class HomeworkSubmissionIntegrationBase(TestCase):
    def setUp(self):
        self.user = self.create_student()
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.enable_homework_comments()
        self.homework = self.create_homework()
        self.create_questions()
        self.client.force_login(self.user)

    def create_student(self):
        return User.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

    def create_course(self):
        return Course.objects.create(
            slug="course",
            title="Course",
            description="Course description",
        )

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def enable_homework_comments(self):
        self.course.homework_problems_comments_field = True
        self.course.save()

    def create_homework(self):
        due_date = timezone.now()
        return Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="Homework 1",
            due_date=due_date,
            homework_url_field=False,
            time_spent_lectures_field=True,
            time_spent_homework_field=True,
            faq_contribution_field=True,
            learning_in_public_cap=2,
        )

    def create_questions(self):
        self.multiple_choice_question = Question.objects.create(
            homework=self.homework,
            text="Pick one option",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers="First option\nSecond option",
        )
        self.free_form_question = Question.objects.create(
            homework=self.homework,
            text="Explain your approach",
            question_type=QuestionTypes.FREE_FORM.value,
        )
        self.checkbox_question = Question.objects.create(
            homework=self.homework,
            text="Pick all matching options",
            question_type=QuestionTypes.CHECKBOXES.value,
            possible_answers="Alpha\nBeta\nGamma",
        )

    def homework_url(self):
        return reverse(
            "homework",
            args=[self.course.slug, self.homework.slug],
        )

    def post_homework(self, post_data):
        homework_url = self.homework_url()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                homework_url,
                post_data,
                HTTP_HOST="localhost",
            )

    def get_submission(self):
        return Submission.objects.get(
            student=self.user,
            homework=self.homework,
        )

    def create_project(self):
        submission_due_date = timezone.now()
        peer_review_due_date = timezone.now()
        return Project.objects.create(
            course=self.course,
            slug="project",
            title="Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def create_project_submission(self, learning_links):
        project = self.create_project()
        return ProjectSubmission.objects.create(
            project=project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            learning_in_public_links=learning_links,
        )

    def assert_submission_exists(self):
        submission_exists = Submission.objects.filter(
            student=self.user,
            homework=self.homework,
        ).exists()
        self.assertTrue(submission_exists)
