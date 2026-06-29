import logging
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from data.models import (
    DatamailerContactEvent,
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
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
    LeaderboardComplaint,
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

    def create_leaderboard_enrollment(
        self,
        username,
        display_name,
        total_score,
        position,
    ):
        return Enrollment.objects.create(
            student=User.objects.create_user(username=username),
            course=self.course,
            display_name=display_name,
            total_score=total_score,
            position_on_leaderboard=position,
        )

    def create_leaderboard_complaint(
        self,
        enrollment,
        reporter,
        issue_type,
        description,
    ):
        return LeaderboardComplaint.objects.create(
            enrollment=enrollment,
            reporter=reporter,
            issue_type=issue_type,
            description=description,
        )

    def create_complaint_reporter(self):
        return User.objects.create_user(
            username="reporter@test.com",
            email="reporter@test.com",
            password="12345",
        )

    def create_complaint_sorting_target(self, reporter):
        first = self.create_leaderboard_enrollment(
            "first@test.com",
            "First Student",
            10,
            2,
        )
        second = self.create_leaderboard_enrollment(
            "second@test.com",
            "Second Student",
            20,
            1,
        )
        self.create_leaderboard_complaint(
            first,
            reporter,
            LeaderboardComplaint.IssueType.HOMEWORK,
            "Incorrect homework.",
        )
        self.create_leaderboard_complaint(
            second,
            reporter,
            LeaderboardComplaint.IssueType.PROJECT,
            "Incorrect project.",
        )
        self.create_leaderboard_complaint(
            second,
            reporter,
            LeaderboardComplaint.IssueType.LEARNING_IN_PUBLIC,
            "Incorrect learning links.",
        )
        return second

    def assert_most_complained_enrollment_first(self, response, enrollment):
        rows = response.context["enrollment_rows"]
        self.assertEqual(rows[0]["enrollment"], enrollment)
        self.assertEqual(rows[0]["enrollment"].open_complaints, 2)

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

    def leaderboard_complaints_url(self):
        return reverse(
            "cadmin_leaderboard_complaints",
            kwargs={"course_slug": self.course.slug},
        )

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

    def create_answer(self, submission, question, answer_text, is_correct):
        return Answer.objects.create(
            submission=submission,
            question=question,
            answer_text=answer_text,
            is_correct=is_correct,
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
        self.create_answer(submission, question1, "5", False)
        self.create_answer(submission, question2, "1", False)
        return submission, question1, question2

    def post_homework_submission_answer_edit(
        self, submission, question1, question2
    ):
        self.login_admin()
        return self.client.post(
            self.homework_submission_edit_url(submission),
            {
                f"answer_{question1.id}": "4",
                f"answer_{question2.id}": "2",
                "learning_in_public_links": (
                    "https://example.com/post1\n"
                    "https://example.com/post2"
                ),
            },
        )

    def assert_homework_submission_scores(
        self, submission, questions_score, learning_in_public_score, total_score
    ):
        self.assertEqual(submission.questions_score, questions_score)
        self.assertEqual(
            submission.learning_in_public_score,
            learning_in_public_score,
        )
        self.assertEqual(submission.total_score, total_score)

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

    def datamailer_operations_url(self):
        return reverse("cadmin_datamailer_operations")

    def create_datamailer_operations_records(self):
        DatamailerOutboxEvent.objects.create(
            event_id="evt-outbox-failed",
            event_type="recipient_list.member_upsert",
            idempotency_key="idem-outbox-failed",
            status=DatamailerOutboxStatus.FAILED,
            last_error="network error",
        )
        DatamailerOutboxDispatchRun.objects.create(
            status=DatamailerOutboxDispatchRunStatus.SUCCESS,
            processed_count=3,
            acked_count=3,
        )
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            status=DatamailerSendAuditStatus.SUCCEEDED,
            idempotency_key="send-ok",
            intended_count=5,
            created_count=4,
            enqueued_count=4,
            skipped_count=1,
        )
        DatamailerSendAudit.objects.create(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            status=DatamailerSendAuditStatus.FAILED,
            idempotency_key="send-failed",
            template_key="course-registration-confirmation",
            error="Datamailer failed",
        )

    def assert_datamailer_operations_content(self, response):
        self.assertContains(response, "Datamailer operations")
        self.assertContains(response, "network error")
        self.assertContains(response, "Datamailer failed")
        self.assertContains(response, reverse("cadmin_datamailer_events"))
        self.assertContains(response, "Bootstrap and repair")
        self.assertContains(
            response,
            "sync_datamailer_contacts --active-only",
        )
        self.assertContains(
            response,
            "sync_datamailer_recipient_lists &lt;kind&gt; --reconcile",
        )
        self.assertContains(
            response,
            "audit_datamailer_recipient_lists &lt;kind&gt; --repair",
        )
        self.assertContains(response, "project-passed")

    def assert_datamailer_send_totals(self, response):
        self.assertEqual(response.context["send_totals"]["intended_count"], 5)
        self.assertEqual(response.context["send_totals"]["created_count"], 4)
        self.assertEqual(response.context["send_totals"]["enqueued_count"], 4)
        self.assertEqual(response.context["send_totals"]["skipped_count"], 1)
        self.assertEqual(response.context["send_totals"]["failed"], 1)

    def create_datamailer_outbox_event(self, event_id, status, last_error):
        return DatamailerOutboxEvent.objects.create(
            event_id=event_id,
            event_type="recipient_list.member_upsert",
            idempotency_key=f"idem-{event_id}",
            status=status,
            last_error=last_error,
        )

    def create_requeue_outbox_events(self):
        return {
            "failed": self.create_datamailer_outbox_event(
                "evt-failed",
                DatamailerOutboxStatus.FAILED,
                "network error",
            ),
            "dead": self.create_datamailer_outbox_event(
                "evt-dead",
                DatamailerOutboxStatus.DEAD,
                "permanent error",
            ),
            "acked": self.create_datamailer_outbox_event(
                "evt-acked",
                DatamailerOutboxStatus.ACKED,
                "old error",
            ),
        }

    def post_datamailer_requeue(self):
        self.login_admin()
        return self.client.post(
            self.datamailer_operations_url(),
            {"action": "requeue"},
        )

    def assert_outbox_event_requeued(self, event):
        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.last_error, "")

    def assert_outbox_event_unchanged(self, event, status, last_error):
        event.refresh_from_db()
        self.assertEqual(event.status, status)
        self.assertEqual(event.last_error, last_error)

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

    def test_datamailer_operations_non_staff_denied(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(self.datamailer_operations_url())

        self.assertEqual(response.status_code, 302)

    def test_datamailer_operations_staff_allowed(self):
        self.create_datamailer_operations_records()

        self.login_admin()
        response = self.client.get(self.datamailer_operations_url())

        self.assertEqual(response.status_code, 200)
        self.assert_datamailer_operations_content(response)
        self.assert_datamailer_send_totals(response)

    def test_datamailer_operations_requeues_failed_and_dead_outbox_events(self):
        events = self.create_requeue_outbox_events()

        response = self.post_datamailer_requeue()

        self.assertRedirects(response, reverse("cadmin_datamailer_operations"))
        self.assert_outbox_event_requeued(events["failed"])
        self.assert_outbox_event_requeued(events["dead"])
        self.assert_outbox_event_unchanged(
            events["acked"],
            DatamailerOutboxStatus.ACKED,
            "old error",
        )

    def test_datamailer_events_non_staff_denied(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(reverse("cadmin_datamailer_events"))

        self.assertEqual(response.status_code, 302)

    def test_datamailer_events_staff_allowed(self):
        DatamailerContactEvent.objects.create(
            event_id="evt-hard-bounce",
            event_type="contact.hard_bounced",
            email="student@example.com",
            client="dtc-courses",
            audience="ml-zoomcamp",
            duplicate_count=2,
        )
        DatamailerContactEvent.objects.create(
            event_id="evt-opened",
            event_type="message.opened",
            email="other@example.com",
            client="dtc-courses",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(reverse("cadmin_datamailer_events"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datamailer events")
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "contact.hard_bounced")
        self.assertContains(response, "ml-zoomcamp")
        self.assertEqual(response.context["metrics"]["total"], 2)
        self.assertEqual(response.context["metrics"]["duplicates"], 2)

    def test_datamailer_events_filters_by_type_and_search(self):
        DatamailerContactEvent.objects.create(
            event_id="evt-hard-bounce",
            event_type="contact.hard_bounced",
            email="student@example.com",
            client="dtc-courses",
            audience="ml-zoomcamp",
        )
        DatamailerContactEvent.objects.create(
            event_id="evt-opened",
            event_type="message.opened",
            email="other@example.com",
            client="dtc-courses",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        response = self.client.get(
            reverse("cadmin_datamailer_events"),
            {"event_type": "contact.hard_bounced", "q": "student"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student@example.com")
        self.assertNotContains(response, "other@example.com")
        self.assertEqual(
            response.context["selected_event_type"],
            "contact.hard_bounced",
        )
        self.assertEqual(response.context["search_query"], "student")

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
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
            marketing_markdown="Old copy",
        )

        self.client.login(
            username="admin@test.com", password="admin123"
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit registration landing page")
        self.assertContains(response, "/register/llm-zoomcamp/")

        response = self.client.post(
            url,
            {
                "title": "LLM Zoomcamp 2026",
                "slug": "llm-zoomcamp",
                "edition_label": "",
                "current_course": self.course.id,
                "is_active": "on",
                "hero_image_url": "",
                "video_url": "",
                "meta_description": "",
                "marketing_markdown": "New copy",
            },
        )

        self.assertRedirects(response, url)
        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "LLM Zoomcamp 2026")
        self.assertEqual(campaign.marketing_markdown, "New copy")

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
    @patch("cadmin.views.DatamailerClient.upsert_campaign")
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
    @patch("cadmin.views.DatamailerClient.preview_campaign")
    @patch("cadmin.views.DatamailerClient.upsert_campaign")
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
    @patch("cadmin.views.DatamailerClient.test_send_campaign")
    @patch("cadmin.views.DatamailerClient.upsert_campaign")
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
    @patch("cadmin.views.DatamailerClient.queue_campaign")
    @patch("cadmin.views.DatamailerClient.upsert_campaign")
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
    @patch("cadmin.views.DatamailerClient.cancel_campaign")
    @patch("cadmin.views.DatamailerClient.upsert_campaign")
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

    def test_leaderboard_complaints_sorted_by_open_count(self):
        self.login_admin()
        second = self.create_complaint_sorting_target(
            self.create_complaint_reporter()
        )

        response = self.client.get(self.leaderboard_complaints_url())

        self.assertEqual(response.status_code, 200)
        self.assert_most_complained_enrollment_first(response, second)
        self.assertContains(response, "Second Student")

    def test_staff_can_resolve_leaderboard_complaint(self):
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Reported Student",
            total_score=10,
        )
        complaint = LeaderboardComplaint.objects.create(
            enrollment=enrollment,
            reporter=self.user,
            issue_type=LeaderboardComplaint.IssueType.HOMEWORK,
            description="Incorrect homework.",
        )

        response = self.client.post(
            reverse(
                "cadmin_leaderboard_complaint_resolve",
                kwargs={
                    "course_slug": self.course.slug,
                    "complaint_id": complaint.id,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "cadmin_leaderboard_complaints",
                kwargs={"course_slug": self.course.slug},
            ),
        )
        complaint.refresh_from_db()
        self.assertTrue(complaint.resolved)
        self.assertEqual(complaint.resolved_by, self.admin_user)

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
        self.client.login(
            username="admin@test.com", password="admin123"
        )
        submissions_url = reverse(
            "cadmin_homework_submissions",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        action_url = reverse(
            "cadmin_homework_set_correct_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(
            action_url, {"next": submissions_url}
        )

        self.assertRedirects(response, submissions_url)

        clear_url = reverse(
            "cadmin_homework_clear_correct_answers",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )

        response = self.client.post(
            clear_url, {"next": submissions_url}
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

    @patch("cadmin.views.send_homework_score_notification")
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

    @patch("cadmin.views.send_project_score_notification")
    @patch("cadmin.views.score_project")
    def test_project_score_shows_message(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Test that scoring project shows a message on the course admin page"""
        from courses.projects import ProjectActionStatus

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

    @patch("cadmin.views.send_project_score_notification")
    @patch("cadmin.views.score_project")
    def test_project_score_can_redirect_back_to_project_submissions(
        self,
        score_project_mock,
        send_score_notification,
    ):
        """Scoring from project submissions returns to that page."""
        from courses.projects import ProjectActionStatus

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

    @patch("cadmin.views.send_project_score_notification")
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

    @patch("cadmin.views.send_peer_review_assignment_notification")
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
        self.create_answer(submission, question1, "4", True)
        self.create_answer(submission, question2, "2", True)

        self.login_admin()
        url = self.homework_submission_edit_url(submission)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Homework Submission")
        self.assertContains(response, self.user.username)
        self.assertContains(response, "What is 2+2?")
        self.assertContains(response, "What is the capital of France?")
        self.assertContains(response, 'value="3"')  # total_score
        self.assertContains(response, "Manage enrollment")
        self.assertContains(
            response,
            reverse(
                "cadmin_enrollment_edit",
                kwargs={
                    "course_slug": self.course.slug,
                    "enrollment_id": enrollment.id,
                },
            ),
        )

    def test_homework_submission_edit_post_updates_answers(self):
        """Test that editing homework answers updates the submission correctly"""
        submission, question1, question2 = (
            self.create_homework_submission_edit_fixture()
        )

        response = self.post_homework_submission_answer_edit(
            submission,
            question1,
            question2,
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assert_homework_submission_scores(submission, 2, 2, 4)
        self.assert_answer_updated(submission, question1, "4")
        self.assert_answer_updated(submission, question2, "2")
        self.assert_learning_in_public_links(
            submission,
            [
                "https://example.com/post1",
                "https://example.com/post2",
            ],
        )

    def test_homework_submission_edit_updates_faq_entry_and_score(self):
        """Test that staff can edit FAQ contribution fields."""
        question = self.create_free_form_question(score=10)
        submission = self.create_homework_submission()
        self.create_answer(submission, question, "5", False)

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
        self.create_answer(submission, question, "5", False)

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
