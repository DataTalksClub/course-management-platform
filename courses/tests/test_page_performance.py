"""AC8: per-page query-count regression tests + public-page caches.

Bounds are upper limits (not exact) to avoid flakes; they catch N+1
regressions, not micro-optimizations. Wall-clock p50/p95 is measured
from prod logs + curl (see agent report), not asserted here.
"""

import datetime
import re

from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    Homework,
    HomeworkState,
    ProjectState,
    Question,
    QuestionTypes,
    User,
)
from courses.models.project import Project, ProjectSubmission


def make_course(slug="perf-2026"):
    return Course.objects.create(
        title="Perf Course 2026",
        slug=slug,
        description="perf",
    )


def make_homework(course, slug, state=HomeworkState.OPEN.value):
    homework = Homework.objects.create(
        course=course,
        slug=slug,
        title=slug,
        due_date=timezone.now() + datetime.timedelta(days=7),
        state=state,
    )
    for index in range(3):
        Question.objects.create(
            homework=homework,
            text=f"Q{index}",
            question_type=QuestionTypes.FREE_FORM.value,
        )
    return homework


def make_project(course, slug="proj1"):
    return Project.objects.create(
        course=course,
        slug=slug,
        title="P1",
        submission_due_date=timezone.now() + datetime.timedelta(days=7),
        peer_review_due_date=timezone.now()
        + datetime.timedelta(days=14),
        state=ProjectState.COLLECTING_SUBMISSIONS.value,
    )


def strip_csrf(content: bytes) -> bytes:
    return re.sub(
        rb'value="[A-Za-z0-9]{32,64}"',
        b'value="TOKEN"',
        content,
    )


class PagePerformanceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.course = make_course()
        self.homework = make_homework(self.course, "hw0")
        make_homework(self.course, "hw1")
        self.project = make_project(self.course)
        self.user = User.objects.create_user(
            username="u@t.com", email="u@t.com", password="x"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="U",
        )

    def assertPage(self, path, max_queries, user=None, status=200):
        if user is not None:
            self.client.force_login(user)
        else:
            self.client.logout()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(path)
        self.assertEqual(response.status_code, status)
        self.assertLessEqual(
            len(ctx),
            max_queries,
            f"{path}: {len(ctx)} queries > {max_queries}",
        )
        return response

    def test_homepage_anon_query_count(self):
        self.assertPage("/", 8)

    def test_course_page_anon_query_count(self):
        self.assertPage(f"/{self.course.slug}/", 12)

    def test_leaderboard_anon_query_count(self):
        self.assertPage(f"/{self.course.slug}/leaderboard", 8)

    def test_breakdown_anon_query_count(self):
        self.assertPage(
            f"/{self.course.slug}/leaderboard/{self.enrollment.id}/", 8
        )

    def test_homework_anon_query_count(self):
        self.assertPage(
            f"/{self.course.slug}/homework/{self.homework.slug}", 8
        )

    def test_project_anon_query_count(self):
        self.assertPage(
            f"/{self.course.slug}/project/{self.project.slug}", 8
        )

    def test_homepage_auth_query_count(self):
        self.assertPage("/", 15, user=self.user)

    def test_course_page_auth_query_count(self):
        self.assertPage(f"/{self.course.slug}/", 20, user=self.user)

    def test_homework_auth_query_count(self):
        self.assertPage(
            f"/{self.course.slug}/homework/{self.homework.slug}",
            15,
            user=self.user,
        )

    def test_project_auth_query_count(self):
        self.assertPage(
            f"/{self.course.slug}/project/{self.project.slug}",
            12,
            user=self.user,
        )

    def test_dashboard_query_count(self):
        make_homework(
            self.course, "hw-scored", state=HomeworkState.SCORED.value
        )
        self.course.first_homework_scored = True
        self.course.save(update_fields=["first_homework_scored"])
        self.assertPage(f"/{self.course.slug}/dashboard", 25)

    @override_settings(
        PUBLIC_PAGE_CACHE_ENABLED=True,
        COURSE_ANON_CACHE_TTL=60,
        HOMEWORK_ANON_CACHE_TTL=60,
        PROJECT_ANON_CACHE_TTL=60,
        DASHBOARD_CACHE_TTL=300,
        LEADERBOARD_BREAKDOWN_CACHE_TTL=300,
    )
    def test_public_caches_hit(self):
        # Course anon: cached context reused, public Cache-Control set.
        first = self.client.get(f"/{self.course.slug}/")
        second = self.client.get(f"/{self.course.slug}/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            strip_csrf(first.content), strip_csrf(second.content)
        )
        self.assertIn("public", second.get("Cache-Control", ""))
        self.assertIsNotNone(
            cache.get(f"course:anon:{self.course.slug}:v2")
        )

        # Homework anon.
        hw_url = f"/{self.course.slug}/homework/{self.homework.slug}"
        first = self.client.get(hw_url)
        second = self.client.get(hw_url)
        self.assertEqual(
            strip_csrf(first.content), strip_csrf(second.content)
        )

        # Project anon.
        proj_url = f"/{self.course.slug}/project/{self.project.slug}"
        first = self.client.get(proj_url)
        second = self.client.get(proj_url)
        self.assertEqual(
            strip_csrf(first.content), strip_csrf(second.content)
        )

        # Breakdown data cached: second render identical modulo CSRF.
        url = f"/{self.course.slug}/leaderboard/{self.enrollment.id}/"
        first = self.client.get(url)
        second = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(
            strip_csrf(first.content), strip_csrf(second.content)
        )
        self.assertIsNotNone(
            cache.get(f"leaderboard:breakdown:{self.enrollment.id}:v1")
        )


class ColdBuildRegressionTestCase(TestCase):
    """Regressions for the ~1 s homepage miss and ~350 ms leaderboard cold
    build (both were dominated by avoidable join/row overhead, measured in
    the agent report)."""

    def setUp(self):
        cache.clear()
        self.course = make_course()
        self.user = User.objects.create_user(
            username="lb@t.com", email="lb@t.com", password="x"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="LB",
            total_score=10,
            position_on_leaderboard=1,
        )

    def test_homepage_queryset_has_no_enrollment_join(self):
        # learner_count (Count over enrollment) multiplied every course row
        # by homeworks x projects x enrollments and made the homepage cache
        # miss render in ~1 s. It is never rendered; the queryset must not
        # touch the enrollment table again.
        from courses.views.course_list import visible_course_list_queryset

        sql = str(visible_course_list_queryset().query).upper()
        self.assertNotIn("ENROLLMENT", sql)

    def test_leaderboard_cold_build_two_queries_exact_shape(self):
        project = make_project(self.course, "proj-lb")
        project.state = ProjectState.COMPLETED.value
        project.save(update_fields=["state"])
        other_user = User.objects.create_user(
            username="lb2@t.com", email="lb2@t.com", password="x"
        )
        hidden_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
            display_name="Hidden",
            display_on_leaderboard=False,
        )
        # Passed first (attempt 1), failed second (attempt 2, skipped).
        ProjectSubmission.objects.create(
            student=self.user,
            enrollment=self.enrollment,
            project=project,
            passed=True,
        )
        ProjectSubmission.objects.create(
            student=self.user,
            enrollment=self.enrollment,
            project=project,
            passed=False,
        )
        ProjectSubmission.objects.create(
            student=other_user,
            enrollment=hidden_enrollment,
            project=project,
            passed=True,
        )

        from courses.views.course_leaderboard_data import (
            build_leaderboard_data,
        )

        with CaptureQueriesContext(connection) as ctx:
            data = build_leaderboard_data(
                self.course, "perf:leaderboard:cold"
            )
        self.assertEqual(
            len(ctx), 2, f"cold build used {len(ctx)} queries"
        )
        self.assertEqual(len(data), 1)
        row = data[0]
        self.assertEqual(row["id"], self.enrollment.id)
        self.assertEqual(row["display_name"], "LB")
        self.assertEqual(row["total_score"], 10)
        self.assertEqual(row["position_on_leaderboard"], 1)
        self.assertEqual(
            row["passed_projects"],
            [{
                "title": project.title,
                "slug": project.slug,
                "attempt": 1,
                "medal_index": 1,
            }],
        )


class StaticConfigTestCase(TestCase):
    def test_static_url_absolute(self):
        from django.conf import settings

        self.assertTrue(settings.STATIC_URL.startswith("/"))

    def test_manifest_storage_configured(self):
        # STATICFILES_STORAGE is legacy on Django 5; STORAGES is
        # authoritative. Prod (non-test) must use the manifest storage so
        # {% static %} emits hashed names served immutable by WhiteNoise.
        import course_management.settings as settings_module
        import inspect

        source = inspect.getsource(settings_module)
        self.assertIn("CompressedManifestStaticFilesStorage", source)
        self.assertIn('"staticfiles"', source)


class HealthAccessLogExclusionTestCase(TestCase):
    def test_health_path_skipped(self):
        from unittest import mock

        from course_management.gunicorn_logging import (
            PrivateAccessLogger,
        )

        self.assertIn(
            "/api/health/",
            PrivateAccessLogger.ACCESS_LOG_EXCLUDED_PATHS,
        )
        logger = PrivateAccessLogger.__new__(PrivateAccessLogger)
        with mock.patch(
            "gunicorn.glogging.Logger.access"
        ) as parent_access:
            logger.access(
                mock.Mock(),
                mock.Mock(),
                {"PATH_INFO": "/api/health/"},
                0.001,
            )
            parent_access.assert_not_called()
            logger.access(
                mock.Mock(), mock.Mock(), {"PATH_INFO": "/"}, 0.001
            )
            self.assertEqual(parent_access.call_count, 1)
