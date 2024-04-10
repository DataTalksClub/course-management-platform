import logging

from django.urls import reverse
from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta

from courses.models import (
    User,
    Course,
    Project,
    ProjectSubmission,
    Enrollment,
    PeerReview,
    PeerReviewState,
    CriteriaResponse,
    ReviewCriteria,
    ReviewCriteriaTypes,
    ProjectState,
    ProjectEvaluationScore,
)


from courses.projects import score_project, ProjectActionStatus

logger = logging.getLogger(__name__)


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectEvaluationTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(**credentials)

        self.course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=timezone.now() - timedelta(days=2),
            peer_review_due_date=timezone.now() - timedelta(hours=1),
            state=ProjectState.PEER_REVIEWING.value,
            points_for_peer_review=10,
            learning_in_public_cap_project=5,
            learning_in_public_cap_review=3,
            number_of_peers_to_evaluate=2,
            points_to_pass=70,
        )

        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/user/project",
            commit_id="1234567",
            learning_in_public_links=["link1", "link2", "link3"],
            faq_contribution="AAAAAAAAAA",
        )

        self.criteria = ReviewCriteria.objects.create(
            course=self.course,
            description="Code quality",
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Satisfactory", "score": 1},
                {"criteria": "Good", "score": 2},
                {"criteria": "Excellent", "score": 3},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.peer_reviews = []
        self.other_peer_reviews = []

        for i in range(3):
            other_user = User.objects.create_user(
                username=f"student{i}",
                email=f"student{i}@email.com",
                password="12345",
            )
            other_enrollment = Enrollment.objects.create(
                student=other_user,
                course=self.course,
            )
            other_submission = ProjectSubmission.objects.create(
                project=self.project,
                student=other_user,
                enrollment=other_enrollment,
                github_link=f"https://github.com/other_student{i}/project",
                commit_id="abcdefg{i}",
            )
            pr = PeerReview.objects.create(
                submission_under_evaluation=self.submission,
                reviewer=other_submission,
                state=PeerReviewState.TO_REVIEW.value,
            )
            self.peer_reviews.append(pr)


    def assert_evaluation_score(
        self, answers_and_scores, expected_project_score
    ):
        for i, (answer, expected_score) in enumerate(
            answers_and_scores
        ):
            pr = self.peer_reviews[i]

            print(f"processing peer review {pr.id}, answer={answer}, expected_score={expected_score}")
            response = CriteriaResponse.objects.create(
                review=pr,
                criteria=self.criteria,
                answer=answer,
            )
            self.assertEqual([expected_score], response.get_scores())

            pr.state = PeerReviewState.SUBMITTED.value
            pr.save()            

        status, message = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.project.refresh_from_db()
        self.assertEqual(
            self.project.state, ProjectState.COMPLETED.value
        )

        score = ProjectEvaluationScore.objects.filter(
            submission=self.submission, review_criteria=self.criteria
        ).first()

        self.assertEqual(score.score, expected_project_score)

        self.submission.refresh_from_db()
        print(self.submission.project_score)
        print(self.submission.total_score)
        self.assertEqual(
            self.submission.project_score, expected_project_score
        )

    def test_project_evaluation_complete_list_top_score(self):
        answers_and_scores = [("4", 3), ("4", 3), ("3", 2)]
        expected_project_score = 3
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_complete_mediam(self):
        answers = ["4", "4", "1"]
        scores = [3, 3, 0]
        expected_project_score = 3

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions(self):
        answers = ["4", "2"]
        scores = [3, 1]
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_two_submissions_round_up(self):
        answers = ["4", "1"]
        scores = [3, 0]
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_one_submission(self):
        answers = ["4"]
        scores = [3]
        expected_project_score = 3

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )

    def test_project_evaluation_zero_submissions_get_median_score_rounded_up(self):
        answers = []
        scores = []
        expected_project_score = 2

        answers_and_scores = list(zip(answers, scores))
        self.assert_evaluation_score(
            answers_and_scores, expected_project_score
        )


    def test_project_not_enough_projects_evaluated(self):
        other_prs = []
        for pr in self.peer_reviews:
            other_pr = PeerReview.objects.create(
                submission_under_evaluation=pr.reviewer,
                reviewer=self.submission,
                state=PeerReviewState.TO_REVIEW.value,
            )
            other_prs.append(other_pr)
        
        status, message = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)
