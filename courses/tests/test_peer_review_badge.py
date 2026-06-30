from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Enrollment,
    Project,
    ProjectState,
    ProjectSubmission,
    PeerReview,
    PeerReviewState,
    ReviewCriteria,
    ReviewCriteriaTypes,
    CriteriaResponse,
)

from courses.project_assignment import ProjectActionStatus
from courses.projects import score_project


class PeerReviewBadgeTests(TestCase):
    """Test cases for peer review badge color changes based on completion status"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="12345",
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        # Create a project in peer review state
        self.pr_project = Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
        )

    def create_submission(self, user, enrollment, repo="test"):
        return ProjectSubmission.objects.create(
            project=self.pr_project,
            student=user,
            enrollment=enrollment,
            github_link=f"https://github.com/{repo}/repo",
        )

    def create_peer_submission(self, index=0):
        other_user = User.objects.create_user(
            username=f"peer{index}@test.com",
            email=f"peer{index}@test.com",
            password="12345",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
        )
        return self.create_submission(
            other_user,
            other_enrollment,
            repo=f"peer{index}",
        )

    def create_submitted_reviews(self, reviewer_submission, count):
        for index in range(count):
            PeerReview.objects.create(
                submission_under_evaluation=self.create_peer_submission(index),
                reviewer=reviewer_submission,
                optional=False,
                state=PeerReviewState.SUBMITTED.value,
                submitted_at=timezone.now(),
            )

    def course_project(self):
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        return projects[0]

    def assert_project_badge(self, expected_class, expected_name):
        project = self.course_project()
        self.assertEqual(project.badge_css_class, expected_class)
        self.assertEqual(project.badge_state_name, expected_name)

    def test_peer_review_badge_red_when_not_completed(self):
        """Test that the badge is red when peer reviews are not completed"""
        submission = self.create_submission(
            self.user,
            self.enrollment,
        )
        self.create_submitted_reviews(submission, 1)

        self.assert_project_badge("bg-danger", "Review")

    def test_peer_review_badge_green_when_completed(self):
        """Test that the badge is green when peer reviews are completed"""
        submission = self.create_submission(
            self.user,
            self.enrollment,
        )
        self.create_submitted_reviews(submission, 3)

        self.assert_project_badge("bg-success", "Review completed")

    def test_peer_review_badge_secondary_when_not_submitted(self):
        """Test that the badge is secondary (gray) when project is not submitted"""
        self.assert_project_badge("bg-secondary", "Not submitted")


class PeerReviewBadgeEndToEndTests(TestCase):
    """End-to-end test for peer review badge showing progression from red to green"""

    def setUp(self):
        self.client = Client()
        self.user = self.create_main_user()
        self.course = self.create_course()
        self.enrollment = self.create_enrollment(self.user)
        self.project = self.create_project()
        self.main_submission = self.create_main_submission()
        self.other_submissions = []
        self.peer_reviews = []
        self.create_peer_review_assignments()
        self.criteria = self.create_review_criteria()

    def create_main_user(self):
        return User.objects.create_user(
            username="main@test.com",
            email="main@test.com",
            password="12345",
        )

    def create_course(self):
        return Course.objects.create(
            title="Test Course",
            slug="test-course",
            project_passing_score=10,
        )

    def create_enrollment(self, user):
        return Enrollment.objects.create(student=user, course=self.course)

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
            number_of_peers_to_evaluate=3,  # Require 3 reviews
            points_for_peer_review=1,
        )

    def create_main_submission(self):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/main/repo",
            commit_id="main123",
        )

    def create_other_user(self, index):
        return User.objects.create_user(
            username=f"student{index}@test.com",
            email=f"student{index}@test.com",
            password="12345",
        )

    def create_other_submission(self, index):
        other_user = self.create_other_user(index)
        other_enrollment = self.create_enrollment(other_user)
        return ProjectSubmission.objects.create(
            project=self.project,
            student=other_user,
            enrollment=other_enrollment,
            github_link=f"https://github.com/student{index}/repo",
            commit_id=f"commit{index}",
        )

    def create_peer_review_assignments(self):
        for index in range(3):
            other_submission = self.create_other_submission(index)
            self.other_submissions.append(other_submission)
            peer_review = self.create_assigned_review(other_submission)
            self.peer_reviews.append(peer_review)
            self.create_submitted_reverse_review(other_submission)

    def create_assigned_review(self, other_submission):
        return PeerReview.objects.create(
            submission_under_evaluation=other_submission,
            reviewer=self.main_submission,
            optional=False,
            state=PeerReviewState.TO_REVIEW.value,
        )

    def create_submitted_reverse_review(self, other_submission):
        return PeerReview.objects.create(
            submission_under_evaluation=self.main_submission,
            reviewer=other_submission,
            optional=False,
            state=PeerReviewState.SUBMITTED.value,
            submitted_at=timezone.now(),
        )

    def create_review_criteria(self):
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Fair", "score": 1},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ],
        )

    def submit_review(self, peer_review, score="3"):
        """Helper to submit a peer review"""
        CriteriaResponse.objects.create(
            review=peer_review,
            criteria=self.criteria,
            answer=score,
        )
        peer_review.state = PeerReviewState.SUBMITTED.value
        peer_review.submitted_at = timezone.now()
        peer_review.save()

    def get_badge_state(self):
        """Helper to get current badge state from course view"""
        self.client.login(username="main@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)

        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        return project.badge_css_class, project.badge_state_name

    def assert_badge_state(self, expected_class, expected_name, message):
        badge_class, badge_name = self.get_badge_state()
        self.assertEqual(badge_class, expected_class, message)
        self.assertEqual(badge_name, expected_name)

    def assert_review_badge_is_red(self, message):
        self.assert_badge_state("bg-danger", "Review", message)

    def assert_review_badge_is_green(self, message):
        self.assert_badge_state(
            "bg-success",
            "Review completed",
            message,
        )

    def move_peer_review_deadline_to_past(self):
        self.project.peer_review_due_date = (
            timezone.now() - timezone.timedelta(hours=1)
        )
        self.project.save()

    def score_project_and_assert_completion(self):
        status, message = score_project(self.project)
        self.assertEqual(
            status,
            ProjectActionStatus.OK,
            f"Scoring should succeed. Got: {message}",
        )
        self.main_submission.refresh_from_db()
        self.assertTrue(
            self.main_submission.reviewed_enough_peers,
            "reviewed_enough_peers should be True after scoring",
        )
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.state,
            ProjectState.COMPLETED.value,
            "Project should be in COMPLETED state after scoring",
        )

    def test_badge_progression_no_reviews_to_all_reviews(self):
        """
        Test badge progression:
        0 reviews -> red
        1 review  -> red
        2 reviews -> red
        3 reviews -> green (after scoring)
        """
        self.assert_review_badge_is_red(
            "Badge should be red when no reviews are submitted"
        )

        self.submit_review(self.peer_reviews[0], "3")
        self.assert_review_badge_is_red(
            "Badge should be red after 1 review (need 3 total)"
        )

        self.submit_review(self.peer_reviews[1], "2")
        self.assert_review_badge_is_red(
            "Badge should be red after 2 reviews (need 3 total)"
        )

        self.submit_review(self.peer_reviews[2], "3")
        self.assert_review_badge_is_green(
            "Badge should be green immediately after all 3 reviews are submitted"
        )

        self.move_peer_review_deadline_to_past()
        self.score_project_and_assert_completion()
