from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.utils import timezone

from courses.admin.projects import (
    ProjectAdmin,
    calculate_statistics_selected_projects,
)
from courses.models import (
    Course,
    Project,
    ProjectState,
    User,
)


class ProjectStatisticsAdminTestCase(TestCase):
    def create_admin_user(self):
        return User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

    def create_course(self):
        return Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

    def create_project(self, *, slug, title, state):
        submission_due_date = timezone.now() + timedelta(days=1)
        peer_review_due_date = timezone.now() + timedelta(days=2)
        return Project.objects.create(
            course=self.course,
            slug=slug,
            title=title,
            description="Test",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=state,
        )

    def create_completed_project(self):
        return self.create_project(
            slug="completed-project",
            title="Completed Project",
            state=ProjectState.COMPLETED.value,
        )

    def create_incomplete_project(self):
        return self.create_project(
            slug="incomplete-project",
            title="Incomplete Project",
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def setUp(self):
        self.site = AdminSite()
        self.admin = ProjectAdmin(Project, self.site)
        self.admin_user = self.create_admin_user()
        self.course = self.create_course()
        self.completed_project = self.create_completed_project()
        self.incomplete_project = self.create_incomplete_project()

    def calculate_selected_projects(self, request, queryset):
        calculate_statistics_selected_projects(self.admin, request, queryset)

    def mock_admin_messages(self):
        self.admin.message_user = Mock()

    def build_admin_request(self):
        request = Mock()
        request.user = self.admin_user
        return request

    def assert_success_message(self):
        self.admin.message_user.assert_called_once()
        args, kwargs = self.admin.message_user.call_args
        self.assertIn("Statistics calculated", args[1])
        self.assertEqual(kwargs["level"], 25)

    def assert_warning_message(self):
        self.admin.message_user.assert_called_once()
        args, kwargs = self.admin.message_user.call_args
        self.assertIn("Cannot calculate statistics", args[1])
        self.assertIn("not been completed", args[1])
        self.assertEqual(kwargs["level"], 30)

    def test_calculate_statistics_admin_action_success(self):
        queryset = Project.objects.filter(id=self.completed_project.id)
        request = self.build_admin_request()
        self.mock_admin_messages()

        with patch(
            "courses.admin.projects.calculate_project_statistics"
        ) as mock_calc:
            mock_calc.return_value = Mock()

            self.calculate_selected_projects(request, queryset)

            mock_calc.assert_called_once_with(
                self.completed_project, force=True
            )
            self.assert_success_message()

    def test_calculate_statistics_admin_action_incomplete_project(self):
        queryset = Project.objects.filter(id=self.incomplete_project.id)
        request = self.build_admin_request()
        self.mock_admin_messages()

        self.calculate_selected_projects(request, queryset)

        self.assert_warning_message()

    def test_calculate_statistics_admin_action_mixed_projects(self):
        queryset = Project.objects.filter(
            id__in=[
                self.completed_project.id,
                self.incomplete_project.id,
            ]
        )
        request = self.build_admin_request()
        self.mock_admin_messages()

        with patch(
            "courses.admin.projects.calculate_project_statistics"
        ) as mock_calc:
            mock_calc.return_value = Mock()

            self.calculate_selected_projects(request, queryset)

            mock_calc.assert_called_once_with(
                self.completed_project, force=True
            )
            self.assertEqual(self.admin.message_user.call_count, 2)

    def test_admin_action_is_registered(self):
        request = Mock()
        request.GET = {}

        actions = self.admin.get_actions(request)
        action_keys = actions.keys()
        action_names = list(action_keys)
        self.assertIn(
            "calculate_statistics_selected_projects", action_names
        )

        action = actions["calculate_statistics_selected_projects"]
        description = action[2]
        self.assertEqual(description, "Calculate statistics")
