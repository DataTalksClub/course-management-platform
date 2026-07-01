from dataclasses import dataclass

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
    HomeworkState,
    ReviewCriteria,
    ReviewCriteriaTypes,
    Project,
    ProjectState,
    ProjectSubmission,
)

from .util import join_possible_answers

credentials = dict(
    username="test@test.com", email="test@test.com", password="12345"
)


@dataclass(frozen=True)
class HomeworkFixtureData:
    slug: str
    title: str
    description: str
    days_due: int
    state: str


@dataclass(frozen=True)
class ProjectFixtureData:
    title: str
    slug: str
    state: str
    submission_days: int


@dataclass(frozen=True)
class ScoredHomeworkExpectation:
    homework: Homework
    submitted: bool
    score: int | None
    with_submitted_at: bool = False


@dataclass(frozen=True)
class OpenHomeworkExpectation:
    homework: Homework
    submitted: bool
    score: int | None
    days_until_due: int


class CourseDetailViewTests(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course", slug="test-course-2"
        )

    def create_enrollment(self, user=None):
        return Enrollment.objects.create(
            student=user or self.user,
            course=self.course,
        )

    def create_homework(self, data: HomeworkFixtureData):
        return Homework.objects.create(
            slug=data.slug,
            course=self.course,
            title=data.title,
            description=data.description,
            due_date=timezone.now() + timezone.timedelta(days=data.days_due),
            state=data.state,
        )

    def create_homeworks(self):
        scored_homework_data = HomeworkFixtureData(
            slug="scored-homework",
            title="Scored Homework",
            description="This homework is already scored.",
            days_due=-1,
            state=HomeworkState.SCORED.value,
        )
        self.homework1 = self.create_homework(scored_homework_data)
        submitted_homework_data = HomeworkFixtureData(
            slug="submitted-homework",
            title="Submitted Homework",
            description="Homework with submitted answers.",
            days_due=7,
            state=HomeworkState.OPEN.value,
        )
        self.homework2 = self.create_homework(submitted_homework_data)
        unscored_homework_data = HomeworkFixtureData(
            slug="unscored-homework",
            title="Homework Without Submissions",
            description="Homework without any submissions yet.",
            days_due=14,
            state=HomeworkState.OPEN.value,
        )
        self.homework3 = self.create_homework(unscored_homework_data)
        self.homeworks = [
            self.homework1,
            self.homework2,
            self.homework3,
        ]

    def create_questions_for_homeworks(self):
        homeworks = self.homeworks
        for homework in homeworks:
            for i in range(1, 4):
                Question.objects.create(
                    homework=homework,
                    text=f"Question {i} of {homework.title}",
                    question_type=QuestionTypes.MULTIPLE_CHOICE.value,
                    possible_answers=join_possible_answers(
                        ["A", "B", "C", "D"]
                    ),
                    correct_answer="1",
                )

    def create_homework_submissions(self):
        self.submission1 = Submission.objects.create(
            homework=self.homework1,
            enrollment=self.enrollment,
            student=self.user,
            total_score=80,
        )
        self.submission2 = Submission.objects.create(
            homework=self.homework2,
            enrollment=self.enrollment,
            student=self.user,
            total_score=0,
        )

    def create_project(self, data: ProjectFixtureData):
        return Project.objects.create(
            course=self.course,
            title=data.title,
            slug=data.slug,
            state=data.state,
            submission_due_date=timezone.now()
            + timezone.timedelta(days=data.submission_days),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_projects(self):
        open_project_data = ProjectFixtureData(
            title="Open Project",
            slug="open-project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
            submission_days=7,
        )
        self.open_project = self.create_project(open_project_data)
        completed_project_data = ProjectFixtureData(
            title="Completed Project",
            slug="completed-project",
            state=ProjectState.COMPLETED.value,
            submission_days=-7,
        )
        self.completed_project = self.create_project(completed_project_data)

    def create_project_submissions(self):
        ProjectSubmission.objects.create(
            project=self.completed_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            project_score=85,
        )

        ProjectSubmission.objects.create(
            project=self.open_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo2",
        )

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.create_homeworks()
        self.create_questions_for_homeworks()
        self.create_homework_submissions()
        self.create_projects()
        self.create_project_submissions()

    def course_url(self):
        return reverse("course", kwargs={"course_slug": self.course.slug})

    def get_course_response(self, login=False):
        if login:
            self.client.login(**credentials)
        return self.client.get(self.course_url())

    def homeworks_by_slug(self, response):
        homeworks_by_slug = {}
        homeworks = response.context["homeworks"]
        for homework in homeworks:
            homeworks_by_slug[homework.slug] = homework
        return homeworks_by_slug

    def assert_course_context(self, context, authenticated):
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertEqual(context["is_authenticated"], authenticated)

    def assert_scored_homework(self, data: ScoredHomeworkExpectation):
        self.assertEqual(data.homework.submitted, data.submitted)
        self.assertEqual(data.homework.is_scored(), True)
        self.assertEqual(data.homework.state, HomeworkState.SCORED.value)
        self.assertEqual(data.homework.score, data.score)
        self.assertEqual(data.homework.days_until_due, 0)
        if not data.with_submitted_at:
            self.assertFalse(hasattr(data.homework, "submitted_at"))

    def assert_open_homework(self, data: OpenHomeworkExpectation):
        self.assertEqual(data.homework.submitted, data.submitted)
        self.assertEqual(data.homework.state, HomeworkState.OPEN.value)
        self.assertEqual(data.homework.is_scored(), False)
        self.assertEqual(data.homework.score, data.score)
        self.assertEqual(data.homework.days_until_due, data.days_until_due)

    def assert_unsubmitted_open_homework(self, homework):
        self.assertFalse(homework.submitted)
        self.assertFalse(hasattr(homework, "submitted_at"))
        self.assertEqual(homework.is_scored(), False)
        self.assertEqual(homework.score, None)
        self.assertEqual(homework.days_until_due, 14)
        self.assertEqual(homework.submissions, [])

    def assert_enrollment_profile_links(self, response):
        self.assertContains(response, "account timezone")
        self.assertContains(
            response,
            f'{reverse("account_settings")}#display-preferences-section',
        )
        self.assertContains(response, "Edit course profile")
        self.assertContains(
            response,
            reverse("enrollment", kwargs={"course_slug": self.course.slug}),
        )

    def assert_no_enrollment_profile_links(self, response):
        self.assertContains(response, "Total score")
        self.assertContains(response, "N/A")
        self.assertNotContains(response, "None")
        self.assertNotContains(response, "Edit course profile")
        self.assertNotContains(
            response,
            reverse("enrollment", kwargs={"course_slug": self.course.slug}),
        )

    def assert_authenticated_homework_summary(self, response):
        homeworks = self.homeworks_by_slug(response)
        scored_expectation = ScoredHomeworkExpectation(
            homework=homeworks["scored-homework"],
            submitted=True,
            score=80,
        )
        self.assert_scored_homework(scored_expectation)

        submitted_homework = homeworks["submitted-homework"]
        open_expectation = OpenHomeworkExpectation(
            homework=submitted_homework,
            submitted=True,
            score=None,
            days_until_due=7,
        )
        self.assert_open_homework(open_expectation)
        self.assertEqual(
            submitted_homework.submitted_at,
            self.submission2.submitted_at,
        )
        self.assert_unsubmitted_open_homework(
            homeworks["unscored-homework"]
        )

    def assert_enrolled_course_context(self, response, total_score):
        self.assertEqual(response.context["total_score"], total_score)
        self.assertTrue(response.context["has_enrollment"])
        self.assert_enrollment_profile_links(response)

    def create_due_homework(self, slug, title, days_due):
        homework_data = HomeworkFixtureData(
            slug=slug,
            title=title,
            description=f"{title} description",
            days_due=days_due,
            state=HomeworkState.OPEN.value,
        )
        homework = self.create_homework(homework_data)
        Question.objects.create(
            homework=homework,
            text=f"Question for {homework.title}",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(["A", "B", "C"]),
            correct_answer="1",
        )
        return homework

    def create_sorted_homework_fixture(self):
        self.create_due_homework("homework-late", "Late Homework", 30)
        self.create_due_homework("homework-early", "Early Homework", 5)
        self.create_due_homework("homework-middle", "Middle Homework", 15)

    def assert_homeworks_in_due_order(self, response):
        homeworks = response.context["homeworks"]
        self.assertEqual(len(homeworks), 6)
        homework_slugs = []
        for homework in homeworks:
            homework_slugs.append(homework.slug)
        early_pos = homework_slugs.index("homework-early")
        middle_pos = homework_slugs.index("homework-middle")
        late_pos = homework_slugs.index("homework-late")
        self.assertLess(early_pos, middle_pos)
        self.assertLess(middle_pos, late_pos)

    def create_peer_review_project(self):
        return Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
        )

    def create_project_submitter(self, project):
        user = User.objects.create_user(
            username="submitted@test.com",
            email="submitted@test.com",
            password="12345",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
        )
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/pr-repo",
        )
        return user

    def assert_course_page_contains_deadline(self, deadline):
        response = self.client.get(self.course_url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn(deadline.strftime("%Y-%m-%d"), content)

    def create_code_quality_criteria(self):
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def create_features_criteria(self):
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            options=[
                {"criteria": "Basic Features", "score": 1},
                {"criteria": "Advanced Features", "score": 2},
            ],
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def create_admin_client(self):
        User.objects.create_superuser(
            username="admin@test.com",
            email="admin@test.com",
            password="admin12345",
        )
        admin_client = Client()
        admin_client.login(
            username="admin@test.com", password="admin12345"
        )
        return admin_client

    def prepare_course_for_duplication(self, year):
        self.course.title = f"Test Course {year - 1}"
        self.course.slug = f"test-course-{year - 1}"
        self.course.social_media_hashtag = "#testcourse2023"
        self.course.faq_document_url = "https://example.com/faq"
        self.course.project_passing_score = 75
        self.course.save()

    def prepare_hidden_course_for_duplication(self, year):
        self.prepare_course_for_duplication(year)
        self.course.visible = False
        self.course.save(update_fields=["visible"])

    def duplicate_course(self, admin_client):
        url = reverse("admin:courses_course_changelist")
        data = {
            "action": "duplicate_course",
            "_selected_action": [str(self.course.pk)],
        }
        return admin_client.post(url, data, follow=True)

    def assert_duplicated_course_fields(self, new_course, year):
        self.assertEqual(new_course.title, f"Test Course {year}")
        self.assertEqual(new_course.description, self.course.description)
        self.assertEqual(
            new_course.social_media_hashtag,
            self.course.social_media_hashtag,
        )
        self.assertEqual(
            new_course.faq_document_url, self.course.faq_document_url
        )
        self.assertEqual(
            new_course.project_passing_score,
            self.course.project_passing_score,
        )
        self.assertFalse(new_course.first_homework_scored)
        self.assertFalse(new_course.finished)

    def assert_duplicated_criteria(
        self, new_course, review_criteria1, review_criteria2
    ):
        new_criteria = new_course.reviewcriteria_set.all()
        self.assertEqual(new_criteria.count(), 2)
        criteria1 = new_criteria.get(description="Code Quality")
        self.assertEqual(criteria1.options, review_criteria1.options)
        self.assertEqual(
            criteria1.review_criteria_type,
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        criteria2 = new_criteria.get(description="Features Implemented")
        self.assertEqual(criteria2.options, review_criteria2.options)
        self.assertEqual(
            criteria2.review_criteria_type,
            ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def test_course_detail_unauthenticated_user(self):
        # Test the view for an unauthenticated user
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertFalse(context["is_authenticated"])
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertIsNone(context["total_score"])

        # Check the properties of each homework in the context
        expected_titles = []
        homeworks = self.homeworks
        for homework in homeworks:
            expected_titles.append(homework.title)
        context_homeworks = context["homeworks"]
        for hw in context_homeworks:
            self.assertIn(hw.title, expected_titles)
            self.assertFalse(hw.submitted)
            self.assertIsNone(hw.score)
            self.assertFalse(hasattr(hw, "submitted_at"))

    def test_course_detail_shows_registration_url(self):
        self.course.start_date = timezone.localdate() + timezone.timedelta(
            days=7
        )
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.save()

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Register")
        self.assertContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )

    def test_course_detail_shows_github_repo_url(self):
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/test-course"
        )
        self.course.save()

        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fab fa-github")
        self.assertContains(response, "GitHub")
        self.assertContains(
            response,
            "https://github.com/DataTalksClub/test-course",
        )

    def test_course_detail_shows_calendar_feed_link(self):
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calendar feed")
        self.assertNotContains(response, "primer-button\">Calendar feed")
        self.assertContains(
            response,
            "All deadlines are shown in your timezone.",
        )
        self.assertNotContains(response, "account timezone")
        self.assertNotContains(
            response,
            f'{reverse("account_settings")}#display-preferences-section',
        )
        self.assertContains(
            response,
            reverse(
                "course_calendar",
                kwargs={"course_slug": self.course.slug},
            ),
        )

    def test_course_detail_does_not_show_time_left_for_scored_homework(self):
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already scored")
        self.assertContains(
            response,
            'app-badge-info px-2 py-0.5 text-xs font-semibold uppercase">Scored',
        )
        self.assertNotContains(response, "Scored:")
        self.assertNotContains(
            response,
            f'data-deadline="{self.homework1.due_date.isoformat()}"',
        )

    def test_course_calendar_feed(self):
        url = reverse(
            "course_calendar",
            kwargs={"course_slug": self.course.slug},
        )

        response = self.client.get(url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "text/calendar; charset=utf-8",
        )
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("VERSION:2.0", content)
        self.assertIn("X-WR-CALNAME:Test Course deadlines", content)
        self.assertIn("SUMMARY:Test Course: Submitted Homework deadline", content)
        self.assertIn("SUMMARY:Test Course: Open Project submission deadline", content)
        self.assertIn("SUMMARY:Test Course: Open Project peer review deadline", content)
        self.assertEqual(content.count("BEGIN:VEVENT"), 7)

    def test_course_detail_authenticated_user(self):
        # Test the view for an authenticated user

        total_score = 80
        self.enrollment.total_score = total_score
        self.enrollment.save()

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assert_course_context(context, authenticated=True)
        self.assert_authenticated_homework_summary(response)
        self.assert_enrolled_course_context(response, total_score)

    def test_course_detail_authenticated_user_not_enrolled(self):
        # Test the view for an authenticated user

        self.enrollment.delete()
        self.course.first_homework_scored = True
        self.course.save(update_fields=["first_homework_scored"])

        response = self.get_course_response(login=True)

        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assert_course_context(context, authenticated=True)
        homeworks = self.homeworks_by_slug(response)

        scored_homework = homeworks["scored-homework"]
        scored_expectation = ScoredHomeworkExpectation(
            homework=scored_homework,
            submitted=False,
            score=None,
        )
        self.assert_scored_homework(scored_expectation)

        submitted_homework = homeworks["submitted-homework"]
        open_expectation = OpenHomeworkExpectation(
            homework=submitted_homework,
            submitted=False,
            score=None,
            days_until_due=7,
        )
        self.assert_open_homework(open_expectation)

        unscored_homework = homeworks["unscored-homework"]
        self.assert_unsubmitted_open_homework(unscored_homework)

        self.assertIsNone(context["total_score"])
        self.assertFalse(context["has_enrollment"])
        self.assert_no_enrollment_profile_links(response)

    def test_course_detail_hides_dashboard_until_first_homework_scored(self):
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Course dashboard")
        self.assertNotContains(
            response,
            reverse("dashboard", kwargs={"course_slug": self.course.slug}),
        )

    def test_course_detail_shows_dashboard_after_first_homework_scored(self):
        self.course.first_homework_scored = True
        self.course.save()
        url = reverse("course", kwargs={"course_slug": self.course.slug})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Course dashboard")
        self.assertContains(
            response,
            reverse("dashboard", kwargs={"course_slug": self.course.slug}),
        )

    def test_not_enrolled_but_can_edit_details(self):
        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "enrollment", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        enrollment = form.instance
        self.assertEqual(enrollment.student.id, self.user.id)

    def test_duplicate_course(self):
        """Test that course duplication works correctly"""
        review_criteria1 = self.create_code_quality_criteria()
        review_criteria2 = self.create_features_criteria()
        admin_client = self.create_admin_client()
        current_year = timezone.now().year
        self.prepare_course_for_duplication(current_year)

        response = self.duplicate_course(admin_client)

        self.assertEqual(response.status_code, 200)
        new_course = Course.objects.get(
            slug=f"test-course-{current_year}"
        )
        self.assert_duplicated_course_fields(new_course, current_year)
        self.assert_duplicated_criteria(
            new_course, review_criteria1, review_criteria2
        )
        self.assertEqual(new_course.students.count(), 0)

    def test_course_view_with_completed_projects(self):
        """Test that the course view shows the 'See all submitted projects' button when there are completed projects"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertTrue(response.context["has_completed_projects"])
        self.assertContains(response, "See all submitted projects")

    def test_course_view_without_completed_projects(self):
        """Test that the course view doesn't show the button when there are no completed projects"""
        # Change the completed project to open state
        self.completed_project.state = (
            ProjectState.COLLECTING_SUBMISSIONS.value
        )
        self.completed_project.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_completed_projects"])
        self.assertNotContains(response, "See all submitted projects")

    def test_course_view_with_certificate(self):
        """Test that the course view shows the certificate download button when a certificate is available"""
        # Set a certificate URL for the enrollment
        self.enrollment.certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertEqual(response.context["certificate_url"], "https://example.com/certificate.pdf")
        self.assertContains(response, "Download Certificate")
        self.assertContains(response, 'href="https://example.com/certificate.pdf"')

    def test_course_view_without_certificate(self):
        """Test that the course view doesn't show the certificate download button when no certificate is available"""
        # Ensure no certificate URL is set
        self.enrollment.certificate_url = None
        self.enrollment.save()

        self.client.login(**credentials)
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")

    def test_course_view_certificate_not_shown_when_not_authenticated(self):
        """Test that the certificate button is not shown to unauthenticated users even if certificate exists"""
        # Set a certificate URL for the enrollment
        self.enrollment.certificate_url = "https://example.com/certificate.pdf"
        self.enrollment.save()

        # Don't login - access as unauthenticated user
        response = self.client.get(
            reverse("course", args=[self.course.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/course.html")
        # certificate_url should be None for unauthenticated users
        self.assertIsNone(response.context["certificate_url"])
        self.assertNotContains(response, "Download Certificate")

    def test_homeworks_sorted_by_due_date(self):
        """Test that homeworks are displayed in order of due date."""
        self.create_sorted_homework_fixture()

        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homeworks_in_due_order(response)

        self.client.login(**credentials)
        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assert_homeworks_in_due_order(response)

    def test_duplicate_course_preserves_visibility(self):
        """Test that course duplication preserves the visibility setting"""
        current_year = timezone.now().year
        self.prepare_hidden_course_for_duplication(current_year)
        admin_client = self.create_admin_client()

        response = self.duplicate_course(admin_client)

        self.assertEqual(response.status_code, 200)
        new_course = Course.objects.get(
            slug=f"test-course-{current_year}"
        )
        self.assertFalse(new_course.visible)

    def test_project_deadline_display_for_peer_review_state(self):
        """Test that the correct deadline is shown based on submission status when project is in PR state"""
        pr_project = self.create_peer_review_project()
        self.create_project_submitter(pr_project)

        self.assert_course_page_contains_deadline(
            pr_project.submission_due_date
        )
        self.client.login(**credentials)
        self.assert_course_page_contains_deadline(
            pr_project.submission_due_date
        )
        self.client.logout()
        self.client.login(username="submitted@test.com", password="12345")
        self.assert_course_page_contains_deadline(
            pr_project.peer_review_due_date
        )

    def test_course_view_does_not_auto_enroll(self):
        """Test that visiting the course page does not auto-enroll a user"""
        # Delete the existing enrollment
        self.enrollment.delete()

        # Verify enrollment is deleted
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0)

        # Login and visit the course page
        self.client.login(**credentials)
        url = reverse("course", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify NO enrollment was created
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0,
                        "Course view should not auto-enroll users")
