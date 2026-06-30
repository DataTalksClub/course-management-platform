from dataclasses import dataclass
from datetime import timedelta
import logging
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectState,
    Enrollment,
    Homework,
    HomeworkState,
    Question,
    AnswerTypes,
    QuestionTypes,
    Submission,
    Answer,
    ReviewCriteria,
    ReviewCriteriaTypes,
    ProjectEvaluationScore,
    RegistrationCampaign,
    CourseRegistration,
)


logger = logging.getLogger(__name__)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


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


class CadminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.create_test_users()
        self.create_course_work_items()
        self.create_review_criteria()

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

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            due_date=timezone.now() + timedelta(days=7),
            state=HomeworkState.OPEN.value,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() + timedelta(days=7),
            peer_review_due_date=timezone.now() + timedelta(days=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def create_review_criteria(self):
        self.criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Problem Description",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 4},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def login_admin(self):
        self.client.login(username="admin@test.com", password="admin123")

    def create_enrollment(self, student=None):
        return Enrollment.objects.create(
            student=student or self.user,
            course=self.course,
        )

    def create_course(self, slug, title, *, finished=False):
        return Course.objects.create(
            slug=slug,
            title=title,
            description=f"{title} Description",
            finished=finished,
        )

    def cadmin_course_list_url(self):
        return reverse("cadmin_course_list")

    def assert_course_list_order(self, response, active_course, finished_course):
        courses = list(response.context["courses"])
        self.assertEqual(courses[:2], [active_course, self.course])
        self.assertEqual(courses[-1], finished_course)

    def assert_course_list_links(self, response):
        self.assertContains(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )
        self.assertContains(
            response,
            reverse("course", kwargs={"course_slug": self.course.slug}),
        )
        self.assertContains(
            response,
            f"/admin/courses/course/{self.course.id}/change/",
        )
        self.assertContains(response, reverse("cadmin_datamailer_operations"))

    def create_homework_submission(self, enrollment=None, **overrides):
        defaults = {
            "homework": self.homework,
            "student": self.user,
            "enrollment": enrollment or self.create_enrollment(),
            "questions_score": 0,
            "faq_score": 0,
            "learning_in_public_score": 0,
            "total_score": 0,
        }
        defaults.update(overrides)
        return Submission.objects.create(**defaults)

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
        return self.client.post(
            self.homework_submission_edit_url(fixture.submission),
            {
                f"answer_{fixture.question1.id}": "4",
                f"answer_{fixture.question2.id}": "2",
                "learning_in_public_links": (
                    "https://example.com/post1\n"
                    "https://example.com/post2"
                ),
            },
        )

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

    def cadmin_project_submissions_url(self):
        return reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
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
        return self.client.post(
            self.homework_action_url(action_name),
            {"next": self.cadmin_homework_submissions_url()},
        )

    def cadmin_course_url(self):
        return reverse(
            "cadmin_course",
            kwargs={"course_slug": self.course.slug},
        )

    def cadmin_course_response(self):
        self.login_admin()
        return self.client.get(self.cadmin_course_url())

    def create_llm_registration_campaign(self, **overrides):
        defaults = {
            "slug": "llm-zoomcamp",
            "title": "LLM Zoomcamp",
            "current_course": self.course,
            "marketing_markdown": "Register now",
        }
        defaults.update(overrides)
        return RegistrationCampaign.objects.create(**defaults)

    def campaign_edit_url(self, campaign):
        return reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

    def campaign_edit_payload(self):
        return {
            "title": "LLM Zoomcamp 2026",
            "slug": "llm-zoomcamp",
            "edition_label": "",
            "current_course": self.course.id,
            "is_active": "on",
            "hero_image_url": "",
            "video_url": "",
            "meta_description": "",
            "marketing_markdown": "New copy",
        }

    def assert_campaign_edit_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit registration landing page")
        self.assertContains(response, "/register/llm-zoomcamp/")

    def assert_campaign_updated(self, campaign):
        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "LLM Zoomcamp 2026")
        self.assertEqual(campaign.marketing_markdown, "New copy")

    def post_campaign_datamailer_action(self, campaign, payload):
        self.login_admin()
        return self.client.post(self.campaign_edit_url(campaign), payload)

    def assert_campaign_draft_upserted(self, upsert_campaign):
        upsert_campaign.assert_called_once()
        self.assertEqual(
            upsert_campaign.call_args.args[0],
            "cmp-registration-llm-zoomcamp",
        )
        payload = upsert_campaign.call_args.args[1]
        self.assertEqual(payload["subject"], "LLM Zoomcamp")
        self.assertEqual(payload["preview_text"], "Learn LLMs")
        self.assertIn("<h2>Register now</h2>", payload["html_body"])
        self.assertEqual(payload["text_body"], "## Register now")
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(payload["recipient_list_key"], self.course.slug)
        self.assertEqual(
            payload["metadata"]["registration_url"],
            "https://courses.example.com/register/llm-zoomcamp/",
        )
        self.assertEqual(
            payload["metadata"]["course_slug"], self.course.slug
        )

    def project_action_url(self, name):
        return reverse(
            name,
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

    def assert_homework_submission_actions(self, response):
        self.assertContains(response, self.homework_url())
        self.assertContains(
            response,
            f"/admin/courses/homework/{self.homework.id}/change/",
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_set_correct_answers"),
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_clear_correct_answers"),
        )
        self.assertContains(
            response,
            self.homework_action_url("cadmin_homework_score"),
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

    def project_url(self):
        return reverse(
            "project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

    def assert_project_submission_actions(self, response):
        self.assertContains(response, self.project_url())
        self.assertContains(
            response,
            f"/admin/courses/project/{self.project.id}/change/",
        )
        self.assertContains(response, "Assign peer reviews")
        self.assertContains(
            response,
            self.project_action_url("cadmin_project_assign_reviews"),
        )

    def assert_project_scoring_action(self, response):
        self.assertContains(response, "Score projects")
        self.assertContains(
            response,
            self.project_action_url("cadmin_project_score"),
        )

    def create_project_submission(self, enrollment=None, **overrides):
        defaults = {
            "project": self.project,
            "student": self.user,
            "enrollment": enrollment or self.create_enrollment(),
            "github_link": "https://github.com/test/repo",
            "commit_id": "abc123",
            "project_score": 0,
            "project_faq_score": 0,
            "project_learning_in_public_score": 0,
            "peer_review_score": 0,
            "peer_review_learning_in_public_score": 0,
            "total_score": 0,
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def create_project_page_submission(self, index):
        user = User.objects.create_user(
            username=f"project-page-student-{index:02d}",
            email=f"project-page-student-{index:02d}@example.com",
            password="test",
        )
        enrollment = self.create_enrollment(student=user)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            total_score=index,
        )

    def create_project_page_submissions(self, count):
        for index in range(count):
            self.create_project_page_submission(index)

    def assert_first_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), 50)
        self.assertContains(response, 'href="?page=2"')
        self.assertContains(response, 'aria-label="Next page"')
        self.assertNotContains(response, "First")
        self.assertNotContains(response, "Last")

    def assert_second_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), 5)
        self.assertContains(response, 'href="?page=1"')
        self.assertContains(response, 'aria-label="Previous page"')

    def create_project_evaluation_scores(self, submission):
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria1,
            score=2,
        )
        ProjectEvaluationScore.objects.create(
            submission=submission,
            review_criteria=self.criteria2,
            score=4,
        )

    def project_submission_edit_url(self, submission):
        return reverse(
            "cadmin_project_submission_edit",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
                "submission_id": submission.id,
            },
        )

    def project_score_payload(self, **overrides):
        payload = {
            f"criteria_score_{self.criteria1.id}": 2,
            f"criteria_score_{self.criteria2.id}": 4,
            "project_faq_score": 5,
            "project_learning_in_public_score": 3,
            "peer_review_score": 7,
            "peer_review_learning_in_public_score": 2,
        }
        payload.update(overrides)
        return payload

    def assert_project_scores(self, submission):
        self.assertEqual(submission.project_score, 6)
        self.assertEqual(submission.project_faq_score, 5)
        self.assertEqual(submission.project_learning_in_public_score, 3)
        self.assertEqual(submission.peer_review_score, 7)
        self.assertEqual(
            submission.peer_review_learning_in_public_score, 2
        )
        self.assertEqual(submission.total_score, 23)

    def assert_project_evaluation_scores(self, submission):
        eval_scores = ProjectEvaluationScore.objects.filter(
            submission=submission
        )
        self.assertEqual(eval_scores.count(), 2)
        criteria1_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria1
        )
        criteria2_score = ProjectEvaluationScore.objects.get(
            submission=submission, review_criteria=self.criteria2
        )
        self.assertEqual(criteria1_score.score, 2)
        self.assertEqual(criteria2_score.score, 4)

    def test_course_list_unauthenticated_redirects(self):
        """Test that unauthenticated users are redirected from course list"""
        response = self.client.get(self.cadmin_course_list_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_course_list_non_staff_denied(self):
        """Test that non-staff users cannot access course list"""
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(self.cadmin_course_list_url())
        self.assertEqual(response.status_code, 302)

    def test_course_list_staff_allowed(self):
        """Test that staff users can access course list"""
        finished_course = self.create_course(
            slug="finished-course",
            title="Finished Course",
            finished=True,
        )
        active_course = self.create_course(
            slug="active-course",
            title="Active Course",
        )

        self.login_admin()
        response = self.client.get(self.cadmin_course_list_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course admin")
        self.assertNotContains(response, 'aria-label="Breadcrumb"')
        self.assert_course_list_order(response, active_course, finished_course)
        self.assert_course_list_links(response)
        self.assertNotContains(response, "> Manage <")
        self.assertNotContains(response, "> View <")

    def test_course_admin_staff_allowed(self):
        """Test that staff users can access course admin page"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course.title)
        self.assertContains(response, "Course admin")
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "Course Admin")
        self.assertContains(
            response,
            reverse("course", kwargs={"course_slug": self.course.slug}),
        )
        self.assertContains(
            response, f"/admin/courses/course/{self.course.id}/change/"
        )
        self.assertContains(response, 'title="View public course page"')
        self.assertContains(response, 'title="Edit in Django Admin"')
        self.assertContains(response, "cadmin-actions-menu")
        self.assertNotContains(response, "Needs attention")
        self.assertNotContains(response, "Course Page")
        self.assertNotContains(response, "Dashboard")

    def test_campaign_registrations_staff_allowed(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=self.course,
            email="student@example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "Europe")

    def test_campaign_create_staff_allowed(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse("cadmin_campaign_create")
        response = self.client.get(f"{url}?course={self.course.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Create registration landing page"
        )
        self.assertContains(response, self.course.title)

        response = self.client.post(
            url,
            {
                "title": "LLM Zoomcamp",
                "slug": "llm-zoomcamp",
                "edition_label": "2026 cohort",
                "current_course": self.course.id,
                "is_active": "on",
                "hero_image_url": "https://example.com/hero.jpg",
                "video_url": "https://youtu.be/example",
                "meta_description": "Learn LLMs",
                "marketing_markdown": "## Register now",
            },
        )

        campaign = RegistrationCampaign.objects.get(slug="llm-zoomcamp")
        self.assertRedirects(
            response,
            reverse(
                "cadmin_campaign_edit",
                kwargs={"campaign_slug": campaign.slug},
            ),
        )
        self.assertEqual(campaign.current_course, self.course)
        self.assertEqual(campaign.marketing_markdown, "## Register now")

    def test_campaign_create_non_staff_denied(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(reverse("cadmin_campaign_create"))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(RegistrationCampaign.objects.exists())

    def test_campaign_edit_staff_allowed(self):
        campaign = self.create_llm_registration_campaign(
            marketing_markdown="Old copy",
        )

        self.login_admin()
        url = self.campaign_edit_url(campaign)
        response = self.client.get(url)

        self.assert_campaign_edit_page(response)

        response = self.client.post(url, self.campaign_edit_payload())

        self.assertRedirects(response, url)
        self.assert_campaign_updated(campaign)

    def test_campaign_edit_shows_datamailer_campaign_controls(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Register now",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_campaign_edit",
                kwargs={"campaign_slug": campaign.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datamailer campaign")
        self.assertContains(response, "cmp-registration-llm-zoomcamp")
        self.assertContains(response, self.course.slug)
        self.assertContains(response, "Sync draft")
        self.assertContains(response, "Test send")

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch("cadmin.views.campaigns.DatamailerClient.upsert_campaign")
    def test_campaign_edit_syncs_datamailer_campaign_draft(
        self, upsert_campaign
    ):
        campaign = self.create_llm_registration_campaign(
            meta_description="Learn LLMs",
            marketing_markdown="## Register now",
        )
        url = self.campaign_edit_url(campaign)

        response = self.post_campaign_datamailer_action(
            campaign,
            {"datamailer_action": "sync"},
        )

        self.assertRedirects(response, url)
        self.assert_campaign_draft_upserted(upsert_campaign)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("cadmin.views.campaigns.DatamailerClient.preview_campaign")
    @patch("cadmin.views.campaigns.DatamailerClient.upsert_campaign")
    def test_campaign_edit_previews_datamailer_campaign(
        self, upsert_campaign, preview_campaign
    ):
        preview_campaign.return_value = {
            "preview": {
                "subject": "Preview subject",
                "text": "Preview text",
            }
        }
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Register now",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.post(
            reverse(
                "cadmin_campaign_edit",
                kwargs={"campaign_slug": campaign.slug},
            ),
            {"datamailer_action": "preview"},
        )

        self.assertEqual(response.status_code, 200)
        upsert_campaign.assert_called_once()
        preview_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )
        self.assertContains(response, "Preview subject")
        self.assertContains(response, "Preview text")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("cadmin.views.campaigns.DatamailerClient.test_send_campaign")
    @patch("cadmin.views.campaigns.DatamailerClient.upsert_campaign")
    def test_campaign_edit_sends_datamailer_campaign_test(
        self, upsert_campaign, test_send_campaign
    ):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Register now",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.post(
            url,
            {
                "datamailer_action": "test_send",
                "test_recipients": "ops@example.com, reviewer@example.com",
            },
        )

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        test_send_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp",
            ["ops@example.com", "reviewer@example.com"],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("cadmin.views.campaigns.DatamailerClient.queue_campaign")
    @patch("cadmin.views.campaigns.DatamailerClient.upsert_campaign")
    def test_campaign_edit_queues_datamailer_campaign(
        self, upsert_campaign, queue_campaign
    ):
        queue_campaign.return_value = {"recipient_count": 42}
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Register now",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.post(
            url,
            {"datamailer_action": "queue"},
        )

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        queue_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("cadmin.views.campaigns.DatamailerClient.cancel_campaign")
    @patch("cadmin.views.campaigns.DatamailerClient.upsert_campaign")
    def test_campaign_edit_cancels_datamailer_campaign_without_upsert(
        self, upsert_campaign, cancel_campaign
    ):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Register now",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.post(
            url,
            {"datamailer_action": "cancel"},
        )

        self.assertRedirects(response, url)
        upsert_campaign.assert_not_called()
        cancel_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )

    def test_homework_submissions_redirect_from_courses(self):
        """Test that homework submissions view redirects to cadmin"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_project_submissions_redirect_from_courses(self):
        """Test that project submissions view redirects to cadmin"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_homework_submissions_staff_allowed(self):
        """Test that staff users can view homework submissions in cadmin"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.homework.title)

    def test_cadmin_homework_submissions_hides_answer_previews(self):
        """Submission lists stay compact and link to the edit page."""
        answer_text = (
            "This long answer should only be visible after opening the submission."
        )
        submission = self.create_submission_with_answer_preview(answer_text)

        self.login_admin()

        response = self.client.get(self.cadmin_homework_submissions_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "This long answer should only")
        self.assertContains(response, "Open")
        self.assertContains(
            response,
            self.homework_submission_edit_url(submission),
        )

    def test_cadmin_homework_submissions_shows_course_actions(self):
        """Homework submissions page exposes the same homework actions as course admin."""
        self.login_admin()

        response = self.client.get(self.cadmin_homework_submissions_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homework_submission_actions(response)

    def test_homework_actions_can_redirect_back_to_homework_submissions(
        self,
    ):
        self.login_admin()
        submissions_url = self.cadmin_homework_submissions_url()

        response = self.post_homework_action_to_submissions(
            "cadmin_homework_set_correct_answers"
        )
        self.assertRedirects(response, submissions_url)

        response = self.post_homework_action_to_submissions(
            "cadmin_homework_clear_correct_answers"
        )
        self.assertRedirects(response, submissions_url)

    def test_homework_actions_ignore_unsafe_next_redirects(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        action_url = reverse(
            "cadmin_homework_set_correct_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(
            action_url, {"next": "https://example.com/"}
        )

        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

    def test_cadmin_project_submissions_staff_allowed(self):
        """Test that staff users can view project submissions in cadmin"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

    def test_cadmin_project_submissions_shows_project_actions(self):
        """Project submissions page exposes project actions."""
        self.login_admin()
        url = self.cadmin_project_submissions_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_project_submission_actions(response)

        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save(update_fields=["state"])

        response = self.client.get(url)

        self.assert_project_scoring_action(response)

    def test_project_submission_email_links_to_leaderboard_record(self):
        """Project submission email links to the student's leaderboard record."""
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test Student",
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            total_score=10,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_project_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "leaderboard_score_breakdown",
                kwargs={
                    "course_slug": self.course.slug,
                    "enrollment_id": enrollment.id,
                },
            ),
        )

    def test_enrollments_search_finds_records_beyond_first_page(self):
        """Enrollment search is server-side, not limited to the visible page."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index:02d}",
                email=f"student-{index:02d}@example.com",
                password="test",
            )
            Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"Student {index:02d}",
            )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_enrollments",
                kwargs={"course_slug": self.course.slug},
            ),
            {"q": "student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student-29@example.com")
        self.assertNotContains(response, "student-00@example.com")

    def test_homework_submission_search_finds_records_beyond_first_page(
        self,
    ):
        """Homework submission search is server-side across all submissions."""
        from courses.models import Submission

        for index in range(30):
            user = User.objects.create_user(
                username=f"hw-student-{index:02d}",
                email=f"hw-student-{index:02d}@example.com",
                password="test",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            Submission.objects.create(
                homework=self.homework,
                student=user,
                enrollment=enrollment,
                total_score=index,
            )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_homework_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "homework_slug": self.homework.slug,
                },
            ),
            {"q": "hw-student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hw-student-29@example.com")
        self.assertNotContains(response, "hw-student-00@example.com")

    def test_project_submission_search_finds_records_beyond_first_page(
        self,
    ):
        """Project submission search is server-side across all submissions."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"project-student-{index:02d}",
                email=f"project-student-{index:02d}@example.com",
                password="test",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            ProjectSubmission.objects.create(
                project=self.project,
                student=user,
                enrollment=enrollment,
                total_score=index,
            )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse(
                "cadmin_project_submissions",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.project.slug,
                },
            ),
            {"q": "project-student-29"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "project-student-29@example.com")
        self.assertNotContains(
            response, "project-student-00@example.com"
        )

    def test_project_submissions_paginated_by_50(self):
        self.create_project_page_submissions(55)
        self.login_admin()
        url = self.cadmin_project_submissions_url()

        response = self.client.get(url)
        self.assert_first_project_submissions_page(response)

        response = self.client.get(url, {"page": 2})
        self.assert_second_project_submissions_page(response)

    def test_project_submission_edit_get(self):
        """Test that staff users can access the project submission edit page"""
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
        )
        self.create_project_evaluation_scores(submission)

        self.login_admin()
        response = self.client.get(self.project_submission_edit_url(submission))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Project Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Problem Description")
        self.assertContains(response, "Code Quality")
        self.assertContains(response, 'value="6"')
        self.assertContains(response, 'value="23"')

    def test_project_submission_edit_post_calculates_total(self):
        """Test that editing individual criteria scores automatically calculates the total"""
        submission = self.create_project_submission()

        self.login_admin()
        response = self.client.post(
            self.project_submission_edit_url(submission),
            self.project_score_payload(),
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assert_project_scores(submission)
        self.assert_project_evaluation_scores(submission)

    def test_project_submission_edit_post_with_checkboxes(self):
        """Test that editing submission with checkboxes works correctly"""
        submission = self.create_project_submission(
            project_score=6,
            project_faq_score=5,
            project_learning_in_public_score=3,
            peer_review_score=7,
            peer_review_learning_in_public_score=2,
            total_score=23,
            reviewed_enough_peers=False,
            passed=False,
        )

        self.login_admin()
        response = self.client.post(
            self.project_submission_edit_url(submission),
            self.project_score_payload(
                reviewed_enough_peers="on",
                passed="on",
            ),
        )
        self.assertEqual(response.status_code, 302)

        submission.refresh_from_db()
        self.assertTrue(submission.reviewed_enough_peers)
        self.assertTrue(submission.passed)

    @patch("cadmin.views.homework.send_homework_score_notification")
    def test_homework_score_shows_message(
        self, send_score_notification
    ):
        """Test that scoring homework shows a message on the course admin page"""
        self.homework.due_date = timezone.now() - timedelta(hours=1)
        self.homework.save(update_fields=["due_date"])
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_homework_score",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.post(url, follow=True)

        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

        # Check that a message was added
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_called_once_with(self.homework)

    def test_course_admin_shows_most_frequent_answer_action(self):
        self.create_homework_submission()

        response = self.cadmin_course_response()

        self.assertEqual(response.status_code, 200)
        self.assert_homework_submission_actions(response)

    def test_homework_set_correct_answers_uses_most_frequent_answer(
        self,
    ):
        question = self.create_multiple_choice_question(
            text="Pick one",
            possible_answers="A\nB\nC",
            correct_answer="",
        )
        self.create_homework_answer_frequency(question, ["2", "2", "1"])

        self.login_admin()
        response = self.client.post(
            self.homework_action_url(
                "cadmin_homework_set_correct_answers"
            ),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        question.refresh_from_db()
        self.assertEqual(question.correct_answer, "2")
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    def test_homework_clear_correct_answers_removes_all_correct_answers(
        self,
    ):
        first_question = self.create_multiple_choice_question(
            text="Pick one",
            possible_answers="A\nB\nC",
            correct_answer="2",
        )
        second_question = Question.objects.create(
            homework=self.homework,
            text="Explain",
            question_type=QuestionTypes.FREE_FORM.value,
            correct_answer="expected answer",
        )

        self.login_admin()
        response = self.client.post(
            self.homework_action_url(
                "cadmin_homework_clear_correct_answers"
            ),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        first_question.refresh_from_db()
        second_question.refresh_from_db()
        self.assertEqual(first_question.correct_answer, "")
        self.assertEqual(second_question.correct_answer, "")
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_shows_message(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Test that scoring project shows a message on the course admin page"""
        from courses.project_assignment import ProjectActionStatus

        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.post(url, follow=True)

        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

        # Check that a message was added
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_can_redirect_back_to_project_submissions(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Scoring from project submissions returns to that page."""
        from courses.project_assignment import ProjectActionStatus

        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        next_url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        url = reverse(
            "cadmin_project_score",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    def test_project_assign_reviews_shows_message(
        self,
        send_score_notification,
    ):
        """Test that assigning peer reviews shows a message on the course admin page"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.post(url, follow=True)

        # Should redirect to course admin page
        self.assertRedirects(
            response,
            reverse(
                "cadmin_course",
                kwargs={"course_slug": self.course.slug},
            ),
        )

        # Check that a message was added
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        send_score_notification.assert_not_called()

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    def test_project_assign_reviews_can_redirect_back_to_project_submissions(
        self,
        send_assignment_notification,
    ):
        """Assigning reviews from project submissions returns to that page."""
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        next_url = reverse(
            "cadmin_project_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        url = reverse(
            "cadmin_project_assign_reviews",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_assignment_notification.assert_not_called()

    def test_log_as_user_requires_post_request(self):
        """Test that the log as user endpoint requires a POST request"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )

        # Try to access the endpoint with GET - should fail
        url = f"/admin/login/user/{self.user.id}/"
        response = self.client.get(url)

        # Should return 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)

    def test_log_as_user_with_post_request(self):
        """Test that staff can log in as another user with POST request"""
        self.client.login(
            username="admin@test.com", password="admin123"
        )

        # Create enrollment for the user
        Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        # Verify we're logged in as admin
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.admin_user.id),
        )

        # Try to log in as the user with POST
        url = f"/admin/login/user/{self.user.id}/"
        response = self.client.post(url)

        # Should redirect to a page (the login redirect)
        self.assertEqual(response.status_code, 302)

        # After the POST, we should be logged in as the user
        # (The session should have changed to the target user)
        # Note: django-loginas stores the original user in a different session key
        # and switches the current user to the target user

    def test_impersonation_banner_shown_when_logged_in_as_student(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )

        response = self.client.post(
            f"/admin/login/user/{self.user.id}/"
        )

        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("course_list"))

        self.assertContains(response, "impersonation-banner")
        self.assertContains(
            response,
            f"You are logged in as <strong>{self.user.email}</strong>",
            html=True,
        )
        self.assertContains(response, "Return to admin account")
        self.assertContains(response, reverse("stop_impersonating"))

    def test_stop_impersonating_restores_admin_account(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        self.client.post(f"/admin/login/user/{self.user.id}/")

        response = self.client.get(reverse("course_list"))
        self.assertEqual(response.wsgi_request.user, self.user)

        response = self.client.post(reverse("stop_impersonating"))

        self.assertRedirects(response, reverse("cadmin_course_list"))
        response = self.client.get(reverse("course_list"))
        self.assertEqual(response.wsgi_request.user, self.admin_user)
        self.assertNotContains(response, "impersonation-banner")

    def test_stop_impersonating_allows_stale_csrf_token_after_user_switch(
        self,
    ):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(
            username="admin@test.com", password="admin123"
        )

        response = csrf_client.get(reverse("course_list"))
        self.assertEqual(response.status_code, 200)
        admin_csrf_token = csrf_client.cookies["csrftoken"].value

        response = csrf_client.post(
            f"/admin/login/user/{self.user.id}/",
            {"csrfmiddlewaretoken": admin_csrf_token},
        )
        self.assertEqual(response.status_code, 302)

        response = csrf_client.get(reverse("course_list"))
        self.assertContains(response, "impersonation-banner")
        self.assertEqual(response.wsgi_request.user, self.user)

        response = csrf_client.post(
            reverse("stop_impersonating"),
            {"csrfmiddlewaretoken": admin_csrf_token},
        )

        self.assertRedirects(response, reverse("cadmin_course_list"))
        response = csrf_client.get(reverse("course_list"))
        self.assertEqual(response.wsgi_request.user, self.admin_user)

    def test_staff_cannot_impersonate_other_staff(self):
        """Test that staff users cannot impersonate other staff users"""
        # Create another staff user
        other_staff = User.objects.create_user(
            username="staff2@test.com",
            email="staff2@test.com",
            password="staff123",
            is_staff=True,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )

        # Try to log in as another staff user with POST
        url = f"/admin/login/user/{other_staff.id}/"
        response = self.client.post(url, follow=True)

        # Should be redirected back with an error message
        # Check that we're still logged in as the original admin user
        self.assertEqual(
            response.wsgi_request.user.username, "admin@test.com"
        )

    def test_enrollment_edit_has_login_as_button(self):
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_enrollment_edit",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": enrollment.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in as student")
        self.assertContains(
            response,
            reverse(
                "loginas-user-login", kwargs={"user_id": self.user.id}
            ),
        )
        self.assertContains(
            response,
            f'value="{reverse("course", kwargs={"course_slug": self.course.slug})}"',
        )

    def test_homework_submission_edit_get(self):
        """Test that staff users can access the homework submission edit page"""
        fixture = self.create_homework_submission_edit_page_fixture()

        response = self.homework_submission_edit_response(fixture.submission)

        self.assert_homework_submission_edit_page(response, fixture)

    def test_homework_submission_edit_post_updates_answers(self):
        """Test that editing homework answers updates the submission correctly"""
        fixture = self.create_homework_submission_edit_fixture()

        response = self.post_homework_submission_answer_edit(fixture)

        self.assertEqual(response.status_code, 302)
        fixture.submission.refresh_from_db()
        expected_scores = HomeworkSubmissionScoreExpectation(
            submission=fixture.submission,
            questions_score=2,
            learning_in_public_score=2,
            total_score=4,
        )
        self.assert_homework_submission_scores(expected_scores)
        self.assert_answer_updated(fixture.submission, fixture.question1, "4")
        self.assert_answer_updated(fixture.submission, fixture.question2, "2")
        self.assert_learning_in_public_links(
            fixture.submission,
            [
                "https://example.com/post1",
                "https://example.com/post2",
            ],
        )

    def test_homework_submission_edit_updates_faq_entry_and_score(self):
        """Test that staff can edit FAQ contribution fields."""
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission()
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        self.login_admin()
        faq_entry = "https://gist.github.com/example/not-validated-here"

        response = self.client.post(
            self.homework_submission_edit_url(submission),
            {
                f"answer_{question.id}": "4",
                "learning_in_public_links": "",
                "faq_contribution_url": faq_entry,
                "faq_score": "3",
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.faq_contribution_url, faq_entry)
        self.assertEqual(submission.faq_score, 3)
        self.assertEqual(submission.total_score, 13)

    def test_homework_submission_edit_triggers_leaderboard_update(self):
        """Test that editing homework submission triggers leaderboard recalculation if score changes"""
        enrollment = self.create_enrollment()
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission(
            enrollment=enrollment,
        )
        answer = AnswerData(
            submission=submission,
            question=question,
            answer_text="5",
            is_correct=False,
        )
        self.create_answer(answer)

        enrollment.total_score = 0
        enrollment.position_on_leaderboard = 999
        enrollment.save()

        self.login_admin()
        response = self.client.post(
            self.homework_submission_edit_url(submission),
            {
                f"answer_{question.id}": "4",
                "learning_in_public_links": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.total_score, 10)
