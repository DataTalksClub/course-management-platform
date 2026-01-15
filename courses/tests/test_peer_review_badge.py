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

from courses.projects import score_project, ProjectActionStatus


class PeerReviewBadgeTests(TestCase):
    """Test cases for peer review badge color changes based on completion status"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="test@test.com",
            email="test@test.com",
            password="12345"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course"
        )
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course
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

    def test_peer_review_badge_red_when_not_completed(self):
        """Test that the badge is red when peer reviews are not completed"""
        # Create a submission
        submission = ProjectSubmission.objects.create(
            project=self.pr_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
        )
        
        # Create only 1 peer review (less than number_of_peers_to_evaluate=3)
        other_user = User.objects.create_user(
            username="peer@test.com",
            email="peer@test.com",
            password="12345"
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course
        )
        other_submission = ProjectSubmission.objects.create(
            project=self.pr_project,
            student=other_user,
            enrollment=other_enrollment,
            github_link="https://github.com/peer/repo",
        )
        # Create a submitted peer review (only 1 out of required 3)
        PeerReview.objects.create(
            submission_under_evaluation=other_submission,
            reviewer=submission,
            optional=False,
            state=PeerReviewState.SUBMITTED.value,
            submitted_at=timezone.now()
        )

        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be red (bg-danger) and state should be "Review"
        self.assertEqual(project.badge_css_class, "bg-danger")
        self.assertEqual(project.badge_state_name, "Review")

    def test_peer_review_badge_green_when_completed(self):
        """Test that the badge is green when peer reviews are completed"""
        # Create a submission
        submission = ProjectSubmission.objects.create(
            project=self.pr_project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
        )
        
        # Create 3 peer reviews (matching number_of_peers_to_evaluate default=3)
        for i in range(3):
            other_user = User.objects.create_user(
                username=f"peer{i}@test.com",
                email=f"peer{i}@test.com",
                password="12345"
            )
            other_enrollment = Enrollment.objects.create(
                student=other_user,
                course=self.course
            )
            other_submission = ProjectSubmission.objects.create(
                project=self.pr_project,
                student=other_user,
                enrollment=other_enrollment,
                github_link=f"https://github.com/peer{i}/repo",
            )
            # Create a submitted peer review (main user reviewing others)
            PeerReview.objects.create(
                submission_under_evaluation=other_submission,
                reviewer=submission,
                optional=False,
                state=PeerReviewState.SUBMITTED.value,
                submitted_at=timezone.now()
            )

        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be green (bg-success) and state should be "Review completed"
        self.assertEqual(project.badge_css_class, "bg-success")
        self.assertEqual(project.badge_state_name, "Review completed")

    def test_peer_review_badge_secondary_when_not_submitted(self):
        """Test that the badge is secondary (gray) when project is not submitted"""
        self.client.login(username="test@test.com", password="12345")
        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)

        # Get the project from the context
        projects = response.context["projects"]
        self.assertEqual(len(projects), 1)
        project = projects[0]

        # Badge should be secondary (bg-secondary) when not submitted
        self.assertEqual(project.badge_css_class, "bg-secondary")
        self.assertEqual(project.badge_state_name, "Not submitted")


class PeerReviewBadgeEndToEndTests(TestCase):
    """End-to-end test for peer review badge showing progression from red to green"""

    def setUp(self):
        self.client = Client()
        
        # Create main user
        self.user = User.objects.create_user(
            username="main@test.com",
            email="main@test.com",
            password="12345"
        )
        
        # Create course
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            project_passing_score=10,  # Set a passing score for project scoring
        )
        
        # Create enrollment for main user
        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course
        )
        
        # Create a project in peer review state with 3 required reviews
        self.project = Project.objects.create(
            course=self.course,
            title="Peer Review Project",
            slug="pr-project",
            state=ProjectState.PEER_REVIEWING.value,
            submission_due_date=timezone.now() - timezone.timedelta(days=1),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=7),
            number_of_peers_to_evaluate=3,  # Require 3 reviews
            points_for_peer_review=1,
        )
        
        # Create main user's submission
        self.main_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/main/repo",
            commit_id="main123",
        )
        
        # Create 3 other students and their submissions for the main user to review
        self.other_submissions = []
        self.peer_reviews = []
        
        for i in range(3):
            other_user = User.objects.create_user(
                username=f"student{i}@test.com",
                email=f"student{i}@test.com",
                password="12345"
            )
            
            other_enrollment = Enrollment.objects.create(
                student=other_user,
                course=self.course
            )
            
            other_submission = ProjectSubmission.objects.create(
                project=self.project,
                student=other_user,
                enrollment=other_enrollment,
                github_link=f"https://github.com/student{i}/repo",
                commit_id=f"commit{i}",
            )
            self.other_submissions.append(other_submission)
            
            # Create peer review assignment (main user reviews other students)
            peer_review = PeerReview.objects.create(
                submission_under_evaluation=other_submission,
                reviewer=self.main_submission,
                optional=False,
                state=PeerReviewState.TO_REVIEW.value,
            )
            self.peer_reviews.append(peer_review)
            
            # Create reverse review (other student reviews main user)
            # This ensures main_submission is also in the submissions dict during scoring
            PeerReview.objects.create(
                submission_under_evaluation=self.main_submission,
                reviewer=other_submission,
                optional=False,
                state=PeerReviewState.SUBMITTED.value,
                submitted_at=timezone.now()
            )
        
        # Create review criteria
        self.criteria = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Fair", "score": 1},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ]
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
    
    def test_badge_progression_no_reviews_to_all_reviews(self):
        """
        Test badge progression: 
        0 reviews -> red
        1 review  -> red
        2 reviews -> red
        3 reviews -> green (after scoring)
        """
        # Initial state: 0 reviews submitted, should be red
        badge_class, badge_name = self.get_badge_state()
        self.assertEqual(badge_class, "bg-danger", 
            "Badge should be red when no reviews are submitted")
        self.assertEqual(badge_name, "Review")
        
        # Submit first review, still need 2 more
        self.submit_review(self.peer_reviews[0], "3")
        
        badge_class, badge_name = self.get_badge_state()
        self.assertEqual(badge_class, "bg-danger",
            "Badge should be red after 1 review (need 3 total)")
        self.assertEqual(badge_name, "Review")
        
        # Submit second review, still need 1 more
        self.submit_review(self.peer_reviews[1], "2")
        
        badge_class, badge_name = self.get_badge_state()
        self.assertEqual(badge_class, "bg-danger",
            "Badge should be red after 2 reviews (need 3 total)")
        self.assertEqual(badge_name, "Review")
        
        # Submit third review - all reviews complete
        self.submit_review(self.peer_reviews[2], "3")
        
        # Now badge should be green immediately (calculated on-the-fly)
        badge_class, badge_name = self.get_badge_state()
        self.assertEqual(badge_class, "bg-success",
            "Badge should be green immediately after all 3 reviews are submitted")
        self.assertEqual(badge_name, "Review completed")
        
        # Move peer review due date to the past to allow scoring
        self.project.peer_review_due_date = timezone.now() - timezone.timedelta(hours=1)
        self.project.save()
        
        # Run scoring to update reviewed_enough_peers field in database
        status, message = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK, f"Scoring should succeed. Got: {message}")
        
        # Refresh submission to get updated reviewed_enough_peers
        self.main_submission.refresh_from_db()
        self.assertTrue(self.main_submission.reviewed_enough_peers,
            "reviewed_enough_peers should be True after scoring")
        
        # After scoring, project state becomes COMPLETED
        self.project.refresh_from_db()
        self.assertEqual(self.project.state, ProjectState.COMPLETED.value,
            "Project should be in COMPLETED state after scoring")

