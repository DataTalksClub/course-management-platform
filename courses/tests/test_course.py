from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.core.cache import cache

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    LeaderboardComplaint,
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

    def create_homework(self, slug, title, description, days_due, state):
        return Homework.objects.create(
            slug=slug,
            course=self.course,
            title=title,
            description=description,
            due_date=timezone.now() + timezone.timedelta(days=days_due),
            state=state,
        )

    def create_homeworks(self):
        self.homework1 = self.create_homework(
            "scored-homework",
            "Scored Homework",
            "This homework is already scored.",
            -1,
            HomeworkState.SCORED.value,
        )
        self.homework2 = self.create_homework(
            "submitted-homework",
            "Submitted Homework",
            "Homework with submitted answers.",
            7,
            HomeworkState.OPEN.value,
        )
        self.homework3 = self.create_homework(
            "unscored-homework",
            "Homework Without Submissions",
            "Homework without any submissions yet.",
            14,
            HomeworkState.OPEN.value,
        )
        self.homeworks = [
            self.homework1,
            self.homework2,
            self.homework3,
        ]

    def create_questions_for_homeworks(self):
        for homework in self.homeworks:
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

    def create_project(self, title, slug, state, submission_days):
        return Project.objects.create(
            course=self.course,
            title=title,
            slug=slug,
            state=state,
            submission_due_date=timezone.now()
            + timezone.timedelta(days=submission_days),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_projects(self):
        self.open_project = self.create_project(
            "Open Project",
            "open-project",
            ProjectState.COLLECTING_SUBMISSIONS.value,
            7,
        )
        self.completed_project = self.create_project(
            "Completed Project",
            "completed-project",
            ProjectState.COMPLETED.value,
            -7,
        )

    def create_project_submissions(self):
        self.completed_submission = ProjectSubmission.objects.create(
            project=self.completed_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            project_score=85,
        )

        self.open_submission = ProjectSubmission.objects.create(
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
        return {h.slug: h for h in response.context["homeworks"]}

    def assert_course_context(self, context, authenticated):
        self.assertEqual(context["course"], self.course)
        self.assertEqual(len(context["homeworks"]), 3)
        self.assertEqual(context["is_authenticated"], authenticated)

    def assert_scored_homework(
        self, homework, submitted, score, with_submitted_at=False
    ):
        self.assertEqual(homework.submitted, submitted)
        self.assertEqual(homework.is_scored(), True)
        self.assertEqual(homework.state, HomeworkState.SCORED.value)
        self.assertEqual(homework.score, score)
        self.assertEqual(homework.days_until_due, 0)
        if not with_submitted_at:
            self.assertFalse(hasattr(homework, "submitted_at"))

    def assert_open_homework(
        self, homework, submitted, score, days_until_due
    ):
        self.assertEqual(homework.submitted, submitted)
        self.assertEqual(homework.state, HomeworkState.OPEN.value)
        self.assertEqual(homework.is_scored(), False)
        self.assertEqual(homework.score, score)
        self.assertEqual(homework.days_until_due, days_until_due)

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
        self.assert_scored_homework(
            homeworks["scored-homework"],
            submitted=True,
            score=80,
        )

        submitted_homework = homeworks["submitted-homework"]
        self.assert_open_homework(
            submitted_homework,
            submitted=True,
            score=None,
            days_until_due=7,
        )
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

    def set_homework_score_breakdown_fixture(self):
        self.submission1.questions_score = 7
        self.submission1.faq_score = 2
        self.submission1.learning_in_public_score = 1
        self.submission1.total_score = 10
        self.submission1.learning_in_public_links = [
            "https://example.com/homework-post",
        ]
        self.submission1.faq_contribution_url = (
            "https://github.com/DataTalksClub/faq/pull/266"
        )
        self.submission1.save()

    def set_project_score_breakdown_fixture(self):
        self.completed_submission.project_score = 20
        self.completed_submission.peer_review_score = 5
        self.completed_submission.project_learning_in_public_score = 3
        self.completed_submission.peer_review_learning_in_public_score = 2
        self.completed_submission.project_faq_score = 1
        self.completed_submission.total_score = 31
        self.completed_submission.learning_in_public_links = [
            "https://example.com/project-post",
        ]
        self.completed_submission.faq_contribution_url = (
            "https://github.com/DataTalksClub/faq/issues/266"
        )
        self.completed_submission.save()

    def leaderboard_score_breakdown_url(self, enrollment=None):
        return reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": (enrollment or self.enrollment).id,
            },
        )

    def assert_score_equations(self, response):
        content = " ".join(strip_tags(response.content.decode()).split())
        self.assertIn(
            "Score: 10 = 7 (questions) + 2 (FAQ) + 1 "
            "(learning in public)",
            content,
        )
        self.assertIn(
            "Score: 31 = 20 (project) + 5 (peer review) + 3 "
            "(learning in public / project) + 2 "
            "(learning in public / peer review) + 1 (FAQ)",
            content,
        )

    def assert_score_breakdown_links(self, response):
        self.assertContains(response, "<details", count=2)
        self.assertContains(response, "<summary", count=2)
        self.assertContains(response, "<strong>FAQ URL:</strong>", count=2)
        self.assertContains(response, "View submission", count=2)
        self.assertContains(response, "https://example.com/homework-post")
        self.assertContains(response, "https://example.com/project-post")
        self.assertContains(
            response, "https://github.com/DataTalksClub/faq/pull/266"
        )
        self.assertContains(
            response, "https://github.com/DataTalksClub/faq/issues/266"
        )

    def create_due_homework(self, slug, title, days_due):
        homework = self.create_homework(
            slug,
            title,
            f"{title} description",
            days_due,
            HomeworkState.OPEN.value,
        )
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
        homework_slugs = [homework.slug for homework in homeworks]
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

    def create_archived_course_fixture(self):
        archive_course = Course.objects.create(
            title="Archived Course 2024",
            slug="archived-course-2024",
            description="Past course summary.",
            finished=True,
        )
        Homework.objects.create(
            slug="archived-homework",
            course=archive_course,
            title="Archived Homework",
            due_date=timezone.now(),
            state=HomeworkState.SCORED.value,
        )
        Project.objects.create(
            course=archive_course,
            title="Archived Project",
            slug="archived-project",
            state=ProjectState.COMPLETED.value,
            submission_due_date=timezone.now(),
            peer_review_due_date=timezone.now(),
        )
        return archive_course

    def configure_active_course_metadata(self):
        self.course.start_date = timezone.datetime(2026, 1, 15).date()
        self.course.end_date = timezone.datetime(2026, 4, 15).date()
        self.course.description = "Database-provided course summary."
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/test-course"
        )
        self.course.save()

    def active_course_from_response(self, response):
        return next(
            course for course in response.context["active_courses"]
            if course.slug == self.course.slug
        )

    def course_card_html(self, content, course):
        course_url = reverse("course", kwargs={"course_slug": course.slug})
        link_position = content.index(f'href="{course_url}"')
        card_start = content.rfind("<article", 0, link_position)
        card_end = content.index("</article>", link_position)
        return content[card_start:card_end]

    def course_archive_row_html(self, content, course):
        archive_url = reverse("course", kwargs={"course_slug": course.slug})
        link_position = content.index(f'href="{archive_url}"')
        row_end = content.index("</a>", link_position)
        return content[link_position:row_end]

    def assert_active_course_metadata(self, response):
        course = self.active_course_from_response(response)
        self.assertEqual(course.home_duration_label, "13 weeks")
        self.assertEqual(
            course.home_current_assignment_label,
            "Next assignment",
        )
        self.assertEqual(
            course.home_current_assignment["title"],
            "Submitted Homework",
        )

    def assert_active_course_card(self, response):
        content = response.content.decode()
        course_card = self.course_card_html(content, self.course)
        self.assertNotIn(">Homework</dt>", course_card)
        self.assertNotIn(">Projects</dt>", course_card)

    def assert_archive_course_row(self, response, archive_course):
        content = response.content.decode()
        archive_row = self.course_archive_row_html(content, archive_course)
        self.assertNotIn("homework</span>", archive_row)
        self.assertNotIn("projects</span>", archive_row)

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
        for hw in context["homeworks"]:
            self.assertIn(hw.title, [h.title for h in self.homeworks])
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
        self.assert_scored_homework(
            scored_homework,
            submitted=False,
            score=None,
        )

        submitted_homework = homeworks["submitted-homework"]
        self.assert_open_homework(
            submitted_homework,
            submitted=False,
            score=None,
            days_until_due=7,
        )

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

    def create_leaderboard_enrollment(
        self, name, total_score, position_on_leaderboard=None
    ):
        student = User.objects.create_user(username=name)
        enrollment = Enrollment.objects.create(
            course=self.course,
            student=student,
            display_name=name,
            total_score=total_score,
            position_on_leaderboard=position_on_leaderboard,
        )
        return enrollment

    def create_standard_leaderboard(self):
        self.create_leaderboard_enrollment("Alice", 100, 1)
        self.create_leaderboard_enrollment("Bob", 90, 2)
        self.create_leaderboard_enrollment("Charlie", 80, 3)

    def create_new_enrollment_leaderboard(self):
        return {
            "e1": self.create_leaderboard_enrollment("e1", 0, None),
            "e2": self.create_leaderboard_enrollment("e2", 90, 1),
            "e3": self.create_leaderboard_enrollment("e3", 80, 2),
            "e4": self.create_leaderboard_enrollment("e4", 70, 3),
            "e5": self.create_leaderboard_enrollment("e5", 0, None),
        }

    def set_current_enrollment_leaderboard_position(self, score, position):
        self.enrollment.total_score = score
        self.enrollment.position_on_leaderboard = position
        self.enrollment.save()

    def leaderboard_response(self, *, login=False):
        if login:
            self.client.login(**credentials)
        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        return self.client.get(url)

    def assert_leaderboard_order(self, response, expected_order):
        enrollments = response.context["enrollments"]
        actual_order = [e["display_name"] for e in enrollments]
        self.assertEqual(actual_order, expected_order)

    def assert_leaderboard_positions(self, response, expected_positions):
        enrollments = response.context["enrollments"]
        actual_positions = [
            e["position_on_leaderboard"] for e in enrollments
        ]
        self.assertEqual(actual_positions, expected_positions)

    def assert_current_student_enrollment(self, response):
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNotNone(current_enrollment)
        self.assertEqual(current_enrollment.id, self.enrollment.id)
        self.assertEqual(current_enrollment.display_name, "TestUser")
        self.assertEqual(current_enrollment.total_score, 95)
        self.assertEqual(
            response.context.get("current_student_enrollment_id"),
            self.enrollment.id,
        )

    def assert_current_student_record_visible(self, response):
        self.assertContains(response, "Your Record")
        self.assertContains(response, "Your total score: 95")
        self.assertContains(response, "Position: 2")
        self.assertContains(response, "Display name: TestUser")
        self.assertContains(response, "Jump to my record")
        self.assertContains(response, f"record-{self.enrollment.id}")

    def assert_standard_leaderboard_visible(self, response):
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def test_leaderboard_order(self):
        e1 = self.create_leaderboard_enrollment("e1", 100, 1)
        e2 = self.create_leaderboard_enrollment("e2", 90, 2)
        e3 = self.create_leaderboard_enrollment("e3", 80, 3)
        e4 = self.create_leaderboard_enrollment("e4", 70, 4)
        e5 = self.create_leaderboard_enrollment("e5", 60, 5)

        self.enrollment.total_score = 50
        self.enrollment.position_on_leaderboard = 6
        self.enrollment.save()

        self.client.login(**credentials)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        enrollments = response.context["enrollments"]

        expected_order = [
            e1.display_name,
            e2.display_name,
            e3.display_name,
            e4.display_name,
            e5.display_name,
            self.enrollment.display_name,
        ]

        actual_order = [e['display_name'] for e in enrollments]

        self.assertEqual(actual_order, expected_order)

    def test_new_enrollment_at_the_end_of_leaderboard(self):
        enrollments = self.create_new_enrollment_leaderboard()
        self.set_current_enrollment_leaderboard_position(50, 4)

        response = self.leaderboard_response(login=True)
        self.assertEqual(response.status_code, 200)

        expected_order = [
            enrollments["e2"].display_name,
            enrollments["e3"].display_name,
            enrollments["e4"].display_name,
            self.enrollment.display_name,
            enrollments["e1"].display_name,
            enrollments["e5"].display_name,
        ]
        self.assert_leaderboard_order(response, expected_order)
        self.assert_leaderboard_positions(response, [1, 2, 3, 4, None, None])

    def test_not_enrolled_yet_but_leaderboard_displays(self):
        """Test that the leaderboard displays even when user is not enrolled"""
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)
        self.create_leaderboard_enrollment("e3", 80, 3)
        self.create_leaderboard_enrollment("e4", 70, 4)
        self.create_leaderboard_enrollment("e5", 60, 5)

        self.enrollment.delete()

        self.client.login(**credentials)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Current enrollment should be None (no auto-enrollment)
        current_enrollment = response.context[
            "current_student_enrollment"
        ]
        self.assertIsNone(current_enrollment)

    def test_leaderboard_links_to_score_breakdown_without_flag_button(self):
        self.create_leaderboard_enrollment("e1", 100, 1)

        url = reverse(
            "leaderboard", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "e1")
        self.assertNotContains(response, "Flag this record")

    def test_score_breakdown_has_flag_button(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": target.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flag this record")

    def test_score_breakdown_prompts_owner_to_show_public_profile(self):
        self.client.force_login(self.user)

        url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": self.enrollment.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Show public profile")
        self.assertContains(
            response,
            f'href="{reverse("enrollment", args=[self.course.slug])}"',
        )

    def test_score_breakdown_does_not_prompt_for_other_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.force_login(self.user)

        url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": target.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_does_not_prompt_when_profile_public(self):
        self.enrollment.display_public_profile = True
        self.enrollment.save()
        self.client.force_login(self.user)

        url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": self.enrollment.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_shows_score_equations(self):
        self.set_homework_score_breakdown_fixture()
        self.set_project_score_breakdown_fixture()

        response = self.client.get(self.leaderboard_score_breakdown_url())

        self.assert_score_equations(response)
        self.assert_score_breakdown_links(response)

    def test_authenticated_user_can_report_leaderboard_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.login(**credentials)

        url = reverse(
            "leaderboard_complaint",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": target.id,
            },
        )
        response = self.client.post(
            url,
            {
                "issue_type": LeaderboardComplaint.IssueType.HOMEWORK,
                "description": "Homework score looks incorrect.",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "leaderboard_score_breakdown",
                kwargs={
                    "course_slug": self.course.slug,
                    "enrollment_id": target.id,
                },
            ),
        )
        complaint = LeaderboardComplaint.objects.get(enrollment=target)
        self.assertEqual(complaint.reporter, self.user)
        self.assertEqual(
            complaint.issue_type,
            LeaderboardComplaint.IssueType.HOMEWORK,
        )

    def test_anonymous_user_is_redirected_when_reporting(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        url = reverse(
            "leaderboard_complaint",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": target.id,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

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

    def test_list_all_submissions_view(self):
        """Test the list all submissions view shows submissions in correct order"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/list_all.html")

        # Check that submissions are ordered by score (completed first)
        submissions = response.context["submissions"]
        self.assertEqual(len(submissions), 2)
        self.assertEqual(submissions[0].project, self.completed_project)
        self.assertEqual(submissions[0].display_score, 85)
        self.assertEqual(submissions[1].project, self.open_project)
        self.assertEqual(submissions[1].display_score, -1)

    def test_list_all_submissions_links_student_to_repository(self):
        """Student names link to repositories and leaderboard stays linked."""
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "leaderboard_score_breakdown",
                kwargs={
                    "course_slug": self.course.slug,
                    "enrollment_id": self.enrollment.id,
                },
            ),
        )
        self.assertContains(response, self.completed_submission.github_link)
        self.assertContains(response, 'aria-label="Open repository"')

    def test_list_all_submissions_links_to_each_project_list(self):
        """All project submissions page includes project-level jump links."""
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project lists")
        self.assertContains(
            response,
            reverse(
                "project_list",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.completed_project.slug,
                },
            ),
        )
        self.assertContains(
            response,
            reverse(
                "project_list",
                kwargs={
                    "course_slug": self.course.slug,
                    "project_slug": self.open_project.slug,
                },
            ),
        )

    def test_list_all_submissions_view_is_paginated(self):
        """Test the list all submissions view limits results per page."""
        for index in range(30):
            user = User.objects.create_user(
                username=f"student-{index}",
                email=f"student-{index}@example.com",
                password="12345",
            )
            enrollment = Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"Student {index}",
            )
            ProjectSubmission.objects.create(
                project=self.open_project,
                student=user,
                enrollment=enrollment,
                github_link=f"https://github.com/test/repo-{index}",
            )

        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submissions_page"].paginator.count, 32)
        self.assertEqual(len(response.context["submissions"]), 25)
        self.assertTrue(response.context["submissions_page"].has_next())

    def test_list_all_submissions_view_unauthorized(self):
        """Test that unauthorized users can access the submissions list"""
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)  # see as usual

    def test_submissions_display_format(self):
        """Test that submissions are displayed with correct format and N/A for unevaluated"""
        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "list_all_project_submissions", args=[self.course.slug]
            )
        )
        self.assertEqual(response.status_code, 200)

        submissions = response.context["submissions"]
        our_submissions = {}

        for submission in submissions:
            if submission.enrollment.student == self.user:
                our_submissions[submission.project_id] = submission

        self.assertEqual(len(our_submissions), 2)

        evaluated_submission = our_submissions[
            self.completed_project.id
        ]
        self.assertEqual(
            evaluated_submission.project, self.completed_project
        )
        self.assertEqual(evaluated_submission.display_score, 85)
        self.assertEqual(
            evaluated_submission.enrollment.student, self.user
        )

        open_submission = our_submissions[self.open_project.id]
        self.assertEqual(open_submission.project, self.open_project)
        self.assertEqual(open_submission.display_score, -1)
        self.assertEqual(open_submission.enrollment.student, self.user)

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

    def test_course_visibility_in_list(self):
        """Test that non-visible courses don't appear in the course list"""
        # Create a visible course
        Course.objects.create(
            title="Visible Course",
            slug="visible-course",
            visible=True
        )
        
        # Create a non-visible course
        Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False
        )
        
        # Test the course list view
        url = reverse("course_list")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that visible course is in the list
        active_courses = response.context["active_courses"]
        finished_courses = response.context["finished_courses"]
        all_courses = list(active_courses) + list(finished_courses)
        course_slugs = [course.slug for course in all_courses]
        
        self.assertIn("visible-course", course_slugs)
        self.assertNotIn("hidden-course", course_slugs)

    def test_course_list_shows_active_course_metadata(self):
        archive_course = self.create_archived_course_fixture()
        self.configure_active_course_metadata()

        url = reverse("course_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_active_course_metadata(response)
        self.assertContains(response, "Jan 15, 2026")
        self.assertContains(response, "Apr 15, 2026")
        self.assertContains(response, "13 weeks")
        self.assertContains(response, "Database-provided course summary.")
        self.assertContains(response, "Submitted Homework")
        self.assert_active_course_card(response)
        self.assert_archive_course_row(response, archive_course)
        self.assertNotContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )
        self.assertContains(
            response,
            "https://github.com/DataTalksClub/test-course",
        )
        self.assertNotContains(response, "home-stats-grid")
        self.assertNotContains(response, "Course page")

    def test_course_list_hides_assignment_panel_without_assignments(self):
        empty_course = Course.objects.create(
            title="No Assignment Course",
            slug="no-assignment-course",
            description="Course without assignments.",
        )

        url = reverse("course_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        course_url = reverse(
            "course", kwargs={"course_slug": empty_course.slug}
        )
        course_link_position = content.index(f'href="{course_url}"')
        card_start = content.rfind("<article", 0, course_link_position)
        card_end = content.index("</article>", course_link_position)
        course_card = content[card_start:card_end]
        self.assertNotIn("Current assignment", course_card)
        self.assertNotIn(">TBA</p>", course_card)
        course_card_text = " ".join(strip_tags(course_card).split())
        self.assertNotIn("Dates to be announced", course_card_text)
        self.assertNotIn("TBA", course_card_text)

    def test_course_list_shows_registration_before_course_start(self):
        self.course.start_date = timezone.localdate() + timezone.timedelta(
            days=7
        )
        self.course.end_date = timezone.localdate() + timezone.timedelta(
            days=77
        )
        self.course.registration_url = (
            "https://courses.datatalks.club/test-course/register"
        )
        self.course.save()

        url = reverse("course_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "https://courses.datatalks.club/test-course/register",
        )
    
    def test_hidden_course_accessible_via_direct_link(self):
        """Test that non-visible courses are still accessible via direct link"""
        # Create a non-visible course
        hidden_course = Course.objects.create(
            title="Hidden Course",
            slug="hidden-course",
            visible=False
        )
        
        # Test direct access to the course
        url = reverse("course", kwargs={"course_slug": "hidden-course"})
        response = self.client.get(url)
        
        # Should be accessible
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"], hidden_course)
    
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

    def test_leaderboard_view_does_not_auto_enroll(self):
        """Test that visiting the leaderboard page does not auto-enroll a user"""
        # Create some other users' enrollments
        self.create_leaderboard_enrollment("e1", 100, 1)
        self.create_leaderboard_enrollment("e2", 90, 2)

        # Delete the existing enrollment
        self.enrollment.delete()

        # Verify enrollment is deleted
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0)

        # Login and visit the leaderboard page
        self.client.login(**credentials)
        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Verify NO enrollment was created
        enrollment_count = Enrollment.objects.filter(
            student=self.user,
            course=self.course
        ).count()
        self.assertEqual(enrollment_count, 0,
                        "Leaderboard view should not auto-enroll users")

        # Verify the context shows None for current enrollment
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment,
                         "Current student enrollment should be None when not enrolled")

    def test_leaderboard_unauthenticated_user(self):
        """Test leaderboard for unauthenticated users"""
        # Create some enrollments for the leaderboard
        self.create_leaderboard_enrollment("Alice", 100, 1)
        self.create_leaderboard_enrollment("Bob", 90, 2)
        self.create_leaderboard_enrollment("Charlie", 80, 3)

        # Logout and visit leaderboard without authentication
        self.client.logout()

        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Context checks
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)
        current_enrollment_id = response.context.get("current_student_enrollment_id")
        self.assertIsNone(current_enrollment_id)

        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 4)  # Alice, Bob, Charlie, and self.enrollment

        # HTML content checks - should NOT show "Your Record" section
        self.assertNotContains(response, "Your Record")
        self.assertNotContains(response, "Your total score")
        self.assertNotContains(response, "Display name")
        self.assertNotContains(response, "Jump to your record")

        # Should show the leaderboard with other students
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def test_leaderboard_authenticated_without_enrollment(self):
        """Test leaderboard for authenticated users who are not enrolled"""
        # Create some enrollments for the leaderboard
        self.create_leaderboard_enrollment("Alice", 100, 1)
        self.create_leaderboard_enrollment("Bob", 90, 2)
        self.create_leaderboard_enrollment("Charlie", 80, 3)

        # Delete the test user's enrollment
        self.enrollment.delete()

        # Login and visit leaderboard
        self.client.login(**credentials)

        url = reverse("leaderboard", kwargs={"course_slug": self.course.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Context checks
        current_enrollment = response.context.get("current_student_enrollment")
        self.assertIsNone(current_enrollment)
        current_enrollment_id = response.context.get("current_student_enrollment_id")
        self.assertIsNone(current_enrollment_id)

        enrollments = response.context["enrollments"]
        self.assertEqual(len(enrollments), 3)  # Only Alice, Bob, Charlie

        # HTML content checks - should NOT show "Your Record" section
        self.assertNotContains(response, "Your Record")
        self.assertNotContains(response, "Your total score")
        self.assertNotContains(response, "Display name")
        self.assertNotContains(response, "Jump to your record")

        # Should show the leaderboard with other students
        self.assertContains(response, "Alice")
        self.assertContains(response, "Bob")
        self.assertContains(response, "Charlie")

    def test_leaderboard_authenticated_with_enrollment(self):
        """Test leaderboard for authenticated users who are enrolled"""
        self.create_standard_leaderboard()

        self.enrollment.display_name = "TestUser"
        self.enrollment.total_score = 95
        self.enrollment.position_on_leaderboard = 2
        self.enrollment.save()

        response = self.leaderboard_response(login=True)

        self.assertEqual(response.status_code, 200)
        self.assert_current_student_enrollment(response)
        self.assertEqual(len(response.context["enrollments"]), 4)
        self.assert_current_student_record_visible(response)
        self.assert_standard_leaderboard_visible(response)
        self.assertContains(response, "TestUser")
