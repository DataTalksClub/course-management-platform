import logging
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.admin.sites import AdminSite
from datetime import timedelta
from unittest.mock import patch, Mock

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    ProjectStatistics,
    Enrollment,
    ProjectState,
)

from courses.scoring import (
    calculate_raw_project_statistics,
    calculate_project_statistics,
)

from courses.admin.projects import (
    ProjectAdmin,
    calculate_statistics_selected_projects,
)

logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectStatisticsTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

        # Create a completed project
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

        # Create some test users and enrollments
        self.users = []
        self.enrollments = []
        for i in range(5):
            user = User.objects.create_user(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="password123",
            )
            enrollment = Enrollment.objects.create(
                student=user, course=self.course
            )
            self.users.append(user)
            self.enrollments.append(enrollment)

    def create_project_submission(self, user, enrollment, scores=None):
        """Helper to create a project submission with optional scores"""
        if scores is None:
            scores = {
                "project_score": 10,
                "project_learning_in_public_score": 5,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 2,
                "total_score": 20,
                "time_spent": 10.5,
            }

        submission = ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            **scores,
        )
        return submission

    def create_bulk_submissions(self, submissions_data):
        """Bulk create submissions for better performance"""
        submissions = []
        for i, scores in enumerate(submissions_data):
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[i],
                enrollment=self.enrollments[i],
                github_link=f"https://github.com/student{i}/repo",
                commit_id=f"abc12{i}",
                **scores,
            )
            submissions.append(submission)
        return ProjectSubmission.objects.bulk_create(submissions)

    def test_calculate_raw_project_statistics_basic(self):
        """Test basic raw statistics calculation"""
        # Create submissions with different scores using bulk operation
        submissions_data = [
            {"project_score": 8, "total_score": 15, "time_spent": 8.0},
            {
                "project_score": 12,
                "total_score": 20,
                "time_spent": 12.0,
            },
            {
                "project_score": 10,
                "total_score": 18,
                "time_spent": 10.0,
            },
        ]

        self.create_bulk_submissions(submissions_data)

        stats = calculate_raw_project_statistics(self.project)

        # Check total submissions
        self.assertEqual(stats["total_submissions"], 3)

        # Check project_score statistics
        self.assertEqual(stats["project_score"]["min"], 8)
        self.assertEqual(stats["project_score"]["max"], 12)
        self.assertEqual(stats["project_score"]["avg"], 10.0)

        # Check total_score statistics
        self.assertEqual(stats["total_score"]["min"], 15)
        self.assertEqual(stats["total_score"]["max"], 20)
        self.assertEqual(
            stats["total_score"]["avg"], 17.666666666666668
        )

        # Check time_spent statistics
        self.assertEqual(stats["time_spent"]["min"], 8.0)
        self.assertEqual(stats["time_spent"]["max"], 12.0)
        self.assertEqual(stats["time_spent"]["avg"], 10.0)

    def test_calculate_raw_project_statistics_insufficient_data(self):
        """Test statistics calculation with insufficient data (< 3 submissions)"""
        # Create only 2 submissions
        for i in range(2):
            self.create_project_submission(
                self.users[i], self.enrollments[i]
            )

        stats = calculate_raw_project_statistics(self.project)

        # Should have total_submissions but null stats for insufficient data
        self.assertEqual(stats["total_submissions"], 2)

        # All score fields should have None values
        for field in ["project_score", "total_score", "time_spent"]:
            self.assertIsNone(stats[field]["min"])
            self.assertIsNone(stats[field]["max"])
            self.assertIsNone(stats[field]["avg"])
            self.assertIsNone(stats[field]["q1"])
            self.assertIsNone(stats[field]["median"])
            self.assertIsNone(stats[field]["q3"])

    def test_calculate_raw_project_statistics_with_nulls(self):
        """Test statistics calculation with some null values"""
        # Create submissions with some null time_spent values
        submissions_data = [
            {"project_score": 8, "total_score": 15, "time_spent": None},
            {
                "project_score": 12,
                "total_score": 20,
                "time_spent": 12.0,
            },
            {
                "project_score": 10,
                "total_score": 18,
                "time_spent": 10.0,
            },
            {"project_score": 9, "total_score": 16, "time_spent": 8.0},
        ]

        for i, scores in enumerate(submissions_data):
            self.create_project_submission(
                self.users[i], self.enrollments[i], scores
            )

        stats = calculate_raw_project_statistics(self.project)

        # time_spent should only include non-null values
        self.assertEqual(stats["time_spent"]["min"], 8.0)
        self.assertEqual(stats["time_spent"]["max"], 12.0)
        self.assertEqual(stats["time_spent"]["avg"], 10.0)

        # project_score should include all values
        self.assertEqual(stats["project_score"]["min"], 8)
        self.assertEqual(stats["project_score"]["max"], 12)

    def test_calculate_project_statistics_model_creation(self):
        """Test that calculate_project_statistics creates a ProjectStatistics object"""
        # Create some submissions
        for i in range(3):
            scores = {
                "project_score": 10 + i,
                "total_score": 20 + i,
                "time_spent": 10.0 + i,
            }
            self.create_project_submission(
                self.users[i], self.enrollments[i], scores
            )

        # Should not exist initially
        self.assertFalse(
            ProjectStatistics.objects.filter(
                project=self.project
            ).exists()
        )

        # Calculate statistics
        stats = calculate_project_statistics(self.project)

        # Should create the object
        self.assertTrue(
            ProjectStatistics.objects.filter(
                project=self.project
            ).exists()
        )
        self.assertEqual(stats.project, self.project)
        self.assertEqual(stats.total_submissions, 3)

        # Check that specific fields are populated
        self.assertEqual(stats.min_project_score, 10)
        self.assertEqual(stats.max_project_score, 12)
        self.assertEqual(stats.avg_project_score, 11.0)

    def test_calculate_project_statistics_force_update(self):
        """Test that force=True updates existing statistics"""
        # Create initial submissions using bulk operation
        submissions_data = [
            {
                "project_score": 10,
                "total_score": 20,
                "time_spent": 10.5,
            },
            {
                "project_score": 10,
                "total_score": 20,
                "time_spent": 10.5,
            },
            {
                "project_score": 10,
                "total_score": 20,
                "time_spent": 10.5,
            },
        ]

        self.create_bulk_submissions(submissions_data)

        # Calculate initial statistics
        stats1 = calculate_project_statistics(self.project)
        initial_count = stats1.total_submissions

        # Add another submission
        self.create_project_submission(
            self.users[3], self.enrollments[3]
        )

        # Calculate without force - should not update
        stats2 = calculate_project_statistics(self.project, force=False)
        self.assertEqual(stats2.total_submissions, initial_count)

        # Calculate with force - should update
        stats3 = calculate_project_statistics(self.project, force=True)
        self.assertEqual(stats3.total_submissions, initial_count + 1)

    def test_calculate_project_statistics_uncompleted_project(self):
        """Test that statistics calculation fails for uncompleted projects"""
        # Create a project that's not completed
        incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        with self.assertRaises(ValueError) as context:
            calculate_project_statistics(incomplete_project)

        self.assertIn(
            "Cannot calculate statistics for uncompleted project",
            str(context.exception),
        )

    def test_project_statistics_model_methods(self):
        """Test ProjectStatistics model methods"""
        # Create submissions and statistics
        for i in range(3):
            scores = {
                "project_score": 10 + i,
                "total_score": 20 + i,
                "time_spent": 10.0 + i,
            }
            self.create_project_submission(
                self.users[i], self.enrollments[i], scores
            )

        stats = calculate_project_statistics(self.project)

        # Test get_value method
        self.assertEqual(stats.get_value("project_score", "min"), 10)
        self.assertEqual(stats.get_value("project_score", "max"), 12)
        self.assertEqual(stats.get_value("total_score", "avg"), 21.0)

        # Test get_stat_fields method
        stat_fields = stats.get_stat_fields()
        self.assertIsInstance(stat_fields, list)
        self.assertTrue(len(stat_fields) > 0)

        # Check that it returns tuples with the expected structure
        first_field = stat_fields[0]
        self.assertIsInstance(first_field, tuple)
        self.assertEqual(
            len(first_field), 3
        )  # (name, stats_list, icon)

        field_name, field_stats, field_icon = first_field
        self.assertIsInstance(field_name, str)
        self.assertIsInstance(field_stats, list)
        self.assertIsInstance(field_icon, str)

        # Check individual stat structure
        if field_stats:
            stat_item = field_stats[0]
            self.assertEqual(len(stat_item), 3)  # (value, label, icon)

        # Test __str__ method
        str_representation = str(stats)
        self.assertIn(self.project.slug, str_representation)


class ProjectStatisticsViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

        # Create regular user
        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

        # Create completed project
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

        # Create incomplete project for testing
        self.incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def test_project_statistics_view_success(self):
        """Test successful project statistics view"""
        # Create some submissions and statistics
        enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            total_score=20,
            time_spent=10.0,
        )

        # Mock the calculate_project_statistics function to avoid actual calculation
        with patch(
            "courses.views.project.calculate_project_statistics"
        ) as mock_calc:
            mock_stats = ProjectStatistics(
                project=self.project,
                total_submissions=1,
                min_project_score=10,
                max_project_score=10,
                avg_project_score=10.0,
            )
            mock_calc.return_value = mock_stats

            url = reverse(
                "project_statistics",
                args=[self.course.slug, self.project.slug],
            )
            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Test Project statistics")
            self.assertContains(response, "Total submissions")
            self.assertIn("stats", response.context)
            self.assertEqual(response.context["project"], self.project)
            self.assertEqual(response.context["course"], self.course)

    def test_project_statistics_view_incomplete_project(self):
        """Test project statistics view redirects for incomplete project"""
        url = reverse(
            "project_statistics",
            args=[self.course.slug, self.incomplete_project.slug],
        )
        response = self.client.get(url, follow=True)

        # Should redirect to project page
        self.assertRedirects(
            response,
            reverse(
                "project",
                args=[self.course.slug, self.incomplete_project.slug],
            ),
        )

        # Should show error message
        messages = list(response.context["messages"])
        self.assertTrue(
            any("not completed yet" in str(m) for m in messages)
        )

    def test_project_statistics_view_nonexistent_project(self):
        """Test project statistics view with non-existent project"""
        url = reverse(
            "project_statistics", args=[self.course.slug, "nonexistent"]
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_project_statistics_view_nonexistent_course(self):
        """Test project statistics view with non-existent course"""
        url = reverse(
            "project_statistics",
            args=["nonexistent", self.project.slug],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_project_statistics_template_rendering(self):
        """Test that the template renders correctly"""
        # Create statistics object
        enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            total_score=20,
            time_spent=10.0,
        )

        with patch(
            "courses.views.project.calculate_project_statistics"
        ) as mock_calc:
            mock_stats = ProjectStatistics(
                project=self.project,
                total_submissions=1,
                min_project_score=10,
                max_project_score=10,
                avg_project_score=10.0,
            )
            mock_calc.return_value = mock_stats

            url = reverse(
                "project_statistics",
                args=[self.course.slug, self.project.slug],
            )
            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "projects/stats.html")
            self.assertContains(response, "Test Project statistics")
            self.assertContains(response, "Total submissions")


class ProjectStatisticsIntegrationTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = User.objects.create_user(**credentials)

        cls.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

        cls.project = Project.objects.create(
            course=cls.course,
            slug="test-project",
            title="Test Project",
            description="Test project description",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

        # Create test users and enrollments once
        cls.users = []
        cls.enrollments = []
        users_data = []
        enrollments_data = []

        for i in range(10):
            user_data = User(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="password123",
            )
            users_data.append(user_data)

        cls.users = User.objects.bulk_create(users_data)

        for user in cls.users:
            enrollment_data = Enrollment(
                student=user, course=cls.course
            )
            enrollments_data.append(enrollment_data)

        cls.enrollments = Enrollment.objects.bulk_create(
            enrollments_data
        )

    def setUp(self):
        self.client = Client()
        # Create a shared submission for navigation tests
        self.shared_enrollment = Enrollment.objects.create(
            student=self.user, course=self.course
        )
        self.shared_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.shared_enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abc123",
            project_score=10,
            total_score=20,
            time_spent=10.0,
        )

    def test_full_statistics_workflow(self):
        """Test the complete statistics workflow from submission to view"""
        # Clear any existing submissions from setUp
        ProjectSubmission.objects.filter(project=self.project).delete()

        # Create diverse submissions using bulk operation
        submission_data = [
            {
                "project_score": 5,
                "project_learning_in_public_score": 2,
                "peer_review_score": 1,
                "peer_review_learning_in_public_score": 0,
                "total_score": 8,
                "time_spent": 5.0,
            },
            {
                "project_score": 8,
                "project_learning_in_public_score": 4,
                "peer_review_score": 2,
                "peer_review_learning_in_public_score": 1,
                "total_score": 15,
                "time_spent": 8.0,
            },
            {
                "project_score": 12,
                "project_learning_in_public_score": 6,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 2,
                "total_score": 23,
                "time_spent": 12.0,
            },
            {
                "project_score": 10,
                "project_learning_in_public_score": 5,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 1,
                "total_score": 19,
                "time_spent": 10.0,
            },
            {
                "project_score": 15,
                "project_learning_in_public_score": 8,
                "peer_review_score": 3,
                "peer_review_learning_in_public_score": 2,
                "total_score": 28,
                "time_spent": 15.0,
            },
        ]

        submissions = []
        for i, scores in enumerate(submission_data):
            submission = ProjectSubmission(
                project=self.project,
                student=self.users[i],
                enrollment=self.enrollments[i],
                github_link=f"https://github.com/student{i}/repo",
                commit_id=f"abc12{i}",
                **scores,
            )
            submissions.append(submission)

        ProjectSubmission.objects.bulk_create(submissions)

        # Calculate statistics
        stats = calculate_project_statistics(self.project)

        # Verify statistics were created
        self.assertIsNotNone(stats)
        self.assertEqual(stats.total_submissions, 5)
        self.assertEqual(stats.min_project_score, 5)
        self.assertEqual(stats.max_project_score, 15)
        self.assertEqual(stats.avg_project_score, 10.0)

        # Test the view
        url = reverse(
            "project_statistics",
            args=[self.course.slug, self.project.slug],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5")  # total submissions
        self.assertContains(response, "Project score")
        self.assertContains(response, "Total score")
        self.assertContains(response, "Time spent on project")

        # Verify the statistics link appears on project page when completed
        project_url = reverse(
            "project", args=[self.course.slug, self.project.slug]
        )
        project_response = self.client.get(project_url)
        self.assertContains(project_response, "Project statistics")
        self.assertContains(project_response, url)

    def test_statistics_links_in_navigation(self):
        """Test that statistics links appear in appropriate navigation areas"""
        # Use shared submission created in setUp
        stats_url = reverse(
            "project_statistics",
            args=[self.course.slug, self.project.slug],
        )

        # Test project results page has statistics link
        results_url = reverse(
            "project_results",
            args=[self.course.slug, self.project.slug],
        )
        results_response = self.client.get(results_url)
        self.assertContains(results_response, "Project statistics")
        self.assertContains(results_response, stats_url)

        # Test project list page has statistics link
        list_url = reverse(
            "project_list", args=[self.course.slug, self.project.slug]
        )
        list_response = self.client.get(list_url)
        self.assertContains(list_response, "Project statistics")
        self.assertContains(list_response, stats_url)

    def test_statistics_links_only_for_completed_projects(self):
        """Test that statistics links only appear for completed projects"""
        # Create incomplete project
        incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        stats_url = reverse(
            "project_statistics",
            args=[self.course.slug, incomplete_project.slug],
        )

        # Test project page doesn't show statistics link for incomplete project
        project_url = reverse(
            "project", args=[self.course.slug, incomplete_project.slug]
        )
        project_response = self.client.get(project_url)
        self.assertNotContains(project_response, "Project statistics")
        self.assertNotContains(project_response, stats_url)

        # Test project list page doesn't show statistics link for incomplete project
        list_url = reverse(
            "project_list",
            args=[self.course.slug, incomplete_project.slug],
        )
        list_response = self.client.get(list_url)
        self.assertNotContains(list_response, "Project statistics")
        self.assertNotContains(list_response, stats_url)


class ProjectStatisticsAdminTestCase(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.admin = ProjectAdmin(Project, self.site)

        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            project_passing_score=10,
        )

        # Create completed project
        self.completed_project = Project.objects.create(
            course=self.course,
            slug="completed-project",
            title="Completed Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COMPLETED.value,
        )

        # Create incomplete project
        self.incomplete_project = Project.objects.create(
            course=self.course,
            slug="incomplete-project",
            title="Incomplete Project",
            description="Test",
            submission_due_date=timezone.now() + timedelta(days=1),
            peer_review_due_date=timezone.now() + timedelta(days=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

    def test_calculate_statistics_admin_action_success(self):
        """Test admin action successfully calculates statistics for completed project"""
        queryset = Project.objects.filter(id=self.completed_project.id)
        request = Mock()
        request.user = self.admin_user

        # Mock message_user to capture calls
        self.admin.message_user = Mock()

        # Mock the actual calculation to avoid setup complexity
        with patch(
            "courses.admin.projects.calculate_project_statistics"
        ) as mock_calc:
            mock_calc.return_value = Mock()

            calculate_statistics_selected_projects(
                self.admin, request, queryset
            )

            # Verify the calculation was called with force=True
            mock_calc.assert_called_once_with(
                self.completed_project, force=True
            )

            # Verify success message was sent
            self.admin.message_user.assert_called_once()
            args, kwargs = self.admin.message_user.call_args
            self.assertIn("Statistics calculated", args[1])
            self.assertEqual(kwargs["level"], 25)  # messages.SUCCESS

    def test_calculate_statistics_admin_action_incomplete_project(self):
        """Test admin action shows warning for incomplete project"""
        queryset = Project.objects.filter(id=self.incomplete_project.id)
        request = Mock()
        request.user = self.admin_user

        # Mock message_user to capture calls
        self.admin.message_user = Mock()

        calculate_statistics_selected_projects(
            self.admin, request, queryset
        )

        # Verify warning message was sent
        self.admin.message_user.assert_called_once()
        args, kwargs = self.admin.message_user.call_args
        self.assertIn("Cannot calculate statistics", args[1])
        self.assertIn("not been completed", args[1])
        self.assertEqual(kwargs["level"], 30)  # messages.WARNING

    def test_calculate_statistics_admin_action_mixed_projects(self):
        """Test admin action handles mix of completed and incomplete projects"""
        queryset = Project.objects.filter(
            id__in=[
                self.completed_project.id,
                self.incomplete_project.id,
            ]
        )
        request = Mock()
        request.user = self.admin_user

        # Mock message_user to capture calls
        self.admin.message_user = Mock()

        with patch(
            "courses.admin.projects.calculate_project_statistics"
        ) as mock_calc:
            mock_calc.return_value = Mock()

            calculate_statistics_selected_projects(
                self.admin, request, queryset
            )

            # Should call calculation only once (for completed project)
            mock_calc.assert_called_once_with(
                self.completed_project, force=True
            )

            # Should call message_user twice (once for success, once for warning)
            self.assertEqual(self.admin.message_user.call_count, 2)

    def test_admin_action_is_registered(self):
        """Test that the admin action is properly registered"""
        # Create a proper mock request object with GET attribute
        request = Mock()
        request.GET = {}

        actions = self.admin.get_actions(request)
        action_names = list(actions.keys())
        self.assertIn(
            "calculate_statistics_selected_projects", action_names
        )

        # Test action description
        action_func, name, description = actions[
            "calculate_statistics_selected_projects"
        ]
        self.assertEqual(description, "Calculate statistics")
