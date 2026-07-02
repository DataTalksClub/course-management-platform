import random
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

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
from courses.project_assignment import ProjectActionStatus
from courses.project_scoring import score_project


def fetch_fresh(obj):
    return obj.__class__.objects.get(pk=obj.id)


credentials = dict(
    username="test@test.com",
    email="test@test.com",
    password="12345",
)


class ProjectEvaluationTestBase(TestCase):
    def create_course(self):
        course = Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )
        course.project_passing_score = 70
        course.save()
        return course

    def create_enrollment(self):
        return Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

    def create_project(self):
        submission_due_date = timezone.now() - timedelta(days=2)
        peer_review_due_date = timezone.now() - timedelta(hours=1)
        return Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            submission_due_date=submission_due_date,
            peer_review_due_date=peer_review_due_date,
            state=ProjectState.PEER_REVIEWING.value,
            points_for_peer_review=10,
            learning_in_public_cap_project=5,
            learning_in_public_cap_review=3,
            number_of_peers_to_evaluate=3,
        )

    def create_submission(self):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/user/project",
            commit_id="1234567",
        )

    def create_review_criteria(self):
        return ReviewCriteria.objects.create(
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

    def create_peer_reviews(
        self, number_of_peer_reviews=3, optional=False
    ):
        peer_reviews = []

        for index in range(number_of_peer_reviews):
            other_submission = self.create_peer_review_submission(index)
            peer_review = self.create_peer_review_assignment(
                other_submission,
                optional,
            )
            peer_reviews.append(peer_review)

        return peer_reviews

    def create_peer_review_student(self, index):
        random_suffix = random.randint(0, 1000000)
        return User.objects.create_user(
            username=f"student{index}-{random_suffix}",
            email=f"student{index}{random_suffix}@email.com",
            password="12345",
        )

    def create_peer_review_submission(self, index):
        other_user = self.create_peer_review_student(index)
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
        )
        return ProjectSubmission.objects.create(
            project=self.project,
            student=other_user,
            enrollment=other_enrollment,
            github_link=f"https://github.com/other_student{index}/project",
            commit_id=f"abcdefg{index}",
        )

    def create_peer_review_assignment(self, other_submission, optional):
        return PeerReview.objects.create(
            submission_under_evaluation=self.submission,
            reviewer=other_submission,
            state=PeerReviewState.TO_REVIEW.value,
            optional=optional,
        )

    def submit_score_answers(self, answers_and_scores):
        for index, row in enumerate(answers_and_scores):
            answer, expected_score = row
            peer_review = self.peer_reviews[index]
            response = CriteriaResponse.objects.create(
                review=peer_review,
                criteria=self.criteria,
                answer=answer,
            )
            scores = response.get_scores()
            self.assertEqual([expected_score], scores)

            peer_review.state = PeerReviewState.SUBMITTED.value
            peer_review.save()

    def assert_score_project_completed(self):
        status, _ = score_project(self.project)
        self.assertEqual(status, ProjectActionStatus.OK)

        self.project.refresh_from_db()
        self.assertEqual(
            self.project.state, ProjectState.COMPLETED.value
        )

    def assert_project_evaluation_score(self, expected_project_score):
        score = ProjectEvaluationScore.objects.filter(
            submission=self.submission, review_criteria=self.criteria
        ).first()

        self.assertEqual(score.score, expected_project_score)

    def assert_submission_project_score(self, expected_project_score):
        self.submission.refresh_from_db()
        self.assertEqual(
            self.submission.project_score, expected_project_score
        )

    def assert_evaluation_score(
        self, answers_and_scores, expected_project_score
    ):
        self.submit_score_answers(answers_and_scores)
        self.assert_score_project_completed()
        self.assert_project_evaluation_score(expected_project_score)
        self.assert_submission_project_score(expected_project_score)

    def create_reverse_assignments(self, peer_reviews, optional=False):
        other_reviews = []
        for peer_review in peer_reviews:
            other_review = PeerReview.objects.create(
                submission_under_evaluation=peer_review.reviewer,
                reviewer=self.submission,
                state=PeerReviewState.TO_REVIEW.value,
                optional=optional,
            )
            other_reviews.append(other_review)
        return other_reviews

    def submit_peer_review(self, peer_review, answer):
        response = CriteriaResponse.objects.create(
            review=peer_review,
            criteria=self.criteria,
            answer=answer,
        )
        expected_score = int(answer) - 1
        scores = response.get_scores()
        self.assertEqual([expected_score], scores)

        peer_review.state = PeerReviewState.SUBMITTED.value
        peer_review.save()

    def submit_peer_reviews(self, peer_reviews, answers):
        peer_review_count = len(peer_reviews)
        answer_count = len(answers)
        self.assertEqual(peer_review_count, answer_count)
        for peer_review, answer in zip(peer_reviews, answers):
            self.submit_peer_review(peer_review, answer)

    def submit_reverse_peer_reviews(
        self, peer_reviews, answers, optional=False
    ):
        reverse_reviews = self.create_reverse_assignments(
            peer_reviews,
            optional=optional,
        )
        self.submit_peer_reviews(reverse_reviews, answers)
        return reverse_reviews

    def assert_passed_with_peer_review_scores(
        self, expected_project_score, review_count
    ):
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.passed)
        self.assertEqual(
            self.submission.peer_review_score,
            review_count * self.project.points_for_peer_review,
        )
        self.assertEqual(
            self.submission.total_score,
            expected_project_score
            + review_count * self.project.points_for_peer_review,
        )

    def create_checkbox_criteria(self):
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Project implementation",
            options=[
                {"criteria": "Data cleaning", "score": 1},
                {"criteria": "Feature engineering", "score": 1},
                {"criteria": "Model evaluation", "score": 1},
            ],
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def submit_checkbox_responses(self, checkbox_criteria):
        answers = ["1,3", "2,3", "3"]
        for peer_review, answer in zip(self.peer_reviews, answers):
            CriteriaResponse.objects.create(
                review=peer_review,
                criteria=checkbox_criteria,
                answer=answer,
            )
            peer_review.state = PeerReviewState.SUBMITTED.value
            peer_review.save()

    def project_results_response(self):
        self.client.login(**credentials)
        results_url = reverse(
            "project_results",
            args=[self.course.slug, self.project.slug],
        )
        return self.client.get(results_url)

    def assert_option_vote_counts(self, response):
        score = response.context["scores"][0]
        option_votes = {}
        option_vote_counts = score.option_vote_counts
        for option in option_vote_counts:
            criteria = option["criteria"]
            votes = option["votes"]
            option_votes[criteria] = votes
        self.assertEqual(
            option_votes,
            {
                "Data cleaning": 1,
                "Feature engineering": 1,
                "Model evaluation": 3,
            },
        )

    def assert_option_vote_content(self, response):
        self.assertContains(response, "Data cleaning")
        self.assertContains(response, "Feature engineering")
        self.assertContains(response, "Model evaluation")
        self.assertContains(response, "3 votes")

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(**credentials)
        self.course = self.create_course()
        self.enrollment = self.create_enrollment()
        self.project = self.create_project()
        self.submission = self.create_submission()
        self.criteria = self.create_review_criteria()
        self.peer_reviews = self.create_peer_reviews(3, optional=False)
