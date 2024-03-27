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
)


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
            submission_due_date=timezone.now() - timedelta(hours=1),
            peer_review_due_date=timezone.now() + timedelta(hours=1),
        )

        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link=f"https://github.com/user/project",
            commit_id="1234567",
        )

        self.other_user = User.objects.create_user(
            username=f"student",
            email=f"email@email.com",
            password="12345",
        )

        self.other_enrollment = Enrollment.objects.create(
            student=self.other_user,
            course=self.course,
        )

        self.other_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.other_user,
            enrollment=self.other_enrollment,
            github_link=f"https://github.com/other_student/project",
            commit_id="1234567",
        )

        self.peer_review = PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            optional=False,
        )

        self.criteria1 = ReviewCriteria.objects.create(
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

        self.criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Project documentation",
            options=[
                {"criteria": "None", "score": 0},
                {"criteria": "Basic", "score": 1},
                {"criteria": "Complete", "score": 2},
                {"criteria": "In-depth", "score": 3},
            ],
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

        self.criteria3 = ReviewCriteria.objects.create(
            course=self.course,
            description="Best practices",
            options=[
                {"criteria": "Coding standards", "score": 1},
                {"criteria": "Tests", "score": 1},
                {"criteria": "Logging", "score": 1},
                {"criteria": "Version control", "score": 1},
                {"criteria": "CI/CD", "score": 1},
            ],
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

        self.criteria = [self.criteria1, self.criteria2, self.criteria3]

    def test_eval_submit_not_authenticated(self):
        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_eval_submit_get_authenticated_not_submitted_accepting_responses(
        self,
    ):
        self.client.login(**credentials)
        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])

        course = context["course"]
        self.assertEqual(course, self.course)

        project = context["project"]
        self.assertEqual(project, self.project)

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.TO_REVIEW.value)

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

        criteria_response_pairs = context["criteria_response_pairs"]

        self.assertEqual(len(criteria_response_pairs), 3)
        c1, r1 = criteria_response_pairs[0]
        self.assertEqual(c1, self.criteria1)
        self.assertEqual(r1, None)

        c2, r2 = criteria_response_pairs[1]
        self.assertEqual(c2, self.criteria2)
        self.assertEqual(r2, None)

        c3, r3 = criteria_response_pairs[2]
        self.assertEqual(c3, self.criteria3)
        self.assertEqual(r3, None)

        submission = context["submission"]
        self.assertEqual(
            submission, self.peer_review.submission_under_evaluation
        )

    def test_eval_submit_get_authenticated_not_submitted_not_accepting_responses(
        self,
    ):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        self.client.login(**credentials)

        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertFalse(context["accepting_submissions"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)

        criteria_response_pairs = context["criteria_response_pairs"]

        self.assertEqual(len(criteria_response_pairs), 3)
        c1, r1 = criteria_response_pairs[0]
        self.assertEqual(c1, self.criteria1)
        self.assertEqual(r1, None)

        c2, r2 = criteria_response_pairs[1]
        self.assertEqual(c2, self.criteria2)
        self.assertEqual(r2, None)

        c3, r3 = criteria_response_pairs[2]
        self.assertEqual(c3, self.criteria3)
        self.assertEqual(r3, None)

    def test_eval_submit_get_authenticated_submitted(self):
        r1 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria1,
            answer="1",
        )

        r2 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria2,
            answer="2",
        )

        r3 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria3,
            answer="1,3",
        )

        self.peer_review.state = PeerReviewState.SUBMITTED.value
        self.peer_review.save()

        self.client.login(**credentials)
        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertTrue(context["accepting_submissions"])

        review = context["review"]
        self.assertEqual(review, self.peer_review)
        self.assertEqual(review.state, PeerReviewState.SUBMITTED.value)

        criteria_response_pairs = context["criteria_response_pairs"]
        print(criteria_response_pairs)

        self.assertEqual(len(criteria_response_pairs), 3)
        c1, r1_actual = criteria_response_pairs[0]
        self.assertEqual(c1, self.criteria1)
        self.assertEqual(r1_actual, r1)

        expected_options1 = [
            {
                "criteria": "Poor",
                "score": 0,
                "index": 1,
                "is_selected": True,
            },
            {
                "criteria": "Satisfactory",
                "score": 1,
                "index": 2,
                "is_selected": False,
            },
            {
                "criteria": "Good",
                "score": 2,
                "index": 3,
                "is_selected": False,
            },
            {
                "criteria": "Excellent",
                "score": 3,
                "index": 4,
                "is_selected": False,
            },
        ]

        self.assertEqual(c1.options, expected_options1)

        c2, r2_actual = criteria_response_pairs[1]
        self.assertEqual(c2, self.criteria2)
        self.assertEqual(r2_actual, r2)

        expected_options2 = [
            {
                "criteria": "None",
                "score": 0,
                "index": 1,
                "is_selected": False,
            },
            {
                "criteria": "Basic",
                "score": 1,
                "index": 2,
                "is_selected": True,
            },
            {
                "criteria": "Complete",
                "score": 2,
                "index": 3,
                "is_selected": False,
            },
            {
                "criteria": "In-depth",
                "score": 3,
                "index": 4,
                "is_selected": False,
            },
        ]

        self.assertEqual(c2.options, expected_options2)

        c3, r3_actual = criteria_response_pairs[2]
        self.assertEqual(c3, self.criteria3)
        self.assertEqual(r3_actual, r3)

        expected_options3 = [
            {
                "criteria": "Coding standards",
                "score": 1,
                "index": 1,
                "is_selected": True,
            },
            {
                "criteria": "Tests",
                "score": 1,
                "index": 2,
                "is_selected": False,
            },
            {
                "criteria": "Logging",
                "score": 1,
                "index": 3,
                "is_selected": True,
            },
            {
                "criteria": "Version control",
                "score": 1,
                "index": 4,
                "is_selected": False,
            },
            {
                "criteria": "CI/CD",
                "score": 1,
                "index": 5,
                "is_selected": False,
            },
        ]

        self.assertEqual(c3.options, expected_options3)

    def test_eval_submit_post_not_submitted(self):
        self.client.login(**credentials)

        criteria_responses = CriteriaResponse.objects.filter(
            review=self.peer_review
        )
        self.assertEqual(criteria_responses.count(), 0)

        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.post(
            url,
            {
                "note_to_peer": "Well done!",
                "time_spent_reviewing": "3",
                f"answer_{self.criteria1.id}": "1",
                f"answer_{self.criteria2.id}": "2",
                f"answer_{self.criteria3.id}": "1,3",
                "learning_in_public_links[]": [
                    "http://example.com/page",
                    "http://example.com/page2",
                ],
                "problems_comments": "No problems"
            },
        )

        self.assertEqual(response.status_code, 302)

        self.peer_review = fetch_fresh(self.peer_review)

        self.assertEqual(
            self.peer_review.state, PeerReviewState.SUBMITTED.value
        )
        self.assertEqual(self.peer_review.note_to_peer, "Well done!")
        self.assertEqual(self.peer_review.problems_comments, "No problems")

        learning_in_public_links = (
            self.peer_review.learning_in_public_links
        )

        self.assertEqual(len(learning_in_public_links), 2)
        self.assertEqual(
            learning_in_public_links[0],
            "http://example.com/page",
        )
        self.assertEqual(
            learning_in_public_links[1],
            "http://example.com/page2",
        )

        self.assertEqual(self.peer_review.time_spent_reviewing, 3.0)

        self.assertEqual(criteria_responses.count(), 3)

        c1 = criteria_responses.get(criteria=self.criteria1)
        self.assertEqual(c1.answer, "1")

        c2 = criteria_responses.get(criteria=self.criteria2)
        self.assertEqual(c2.answer, "2")

        c3 = criteria_responses.get(criteria=self.criteria3)
        self.assertEqual(c3.answer, "1,3")

    def test_eval_submit_post_already_submitted(self):
        c1 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria1,
            answer="1",
        )

        c2 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria2,
            answer="2",
        )

        c3 = CriteriaResponse.objects.create(
            review=self.peer_review,
            criteria=self.criteria3,
            answer="1,3",
        )

        self.peer_review.state = PeerReviewState.SUBMITTED.value
        self.peer_review.save()

        self.client.login(**credentials)

        criteria_responses = CriteriaResponse.objects.filter(
            review=self.peer_review
        )
        self.assertEqual(criteria_responses.count(), 3)

        url = reverse(
            "projects_eval_submit",
            args=[
                self.course.slug,
                self.project.slug,
                self.peer_review.id,
            ],
        )

        response = self.client.post(
            url,
            {
                "note_to_peer": "Well done!",
                "time_spent_reviewing": "3",
                f"answer_{self.criteria1.id}": "2",
                f"answer_{self.criteria2.id}": "3",
                f"answer_{self.criteria3.id}": "1,2,3",
                "learning_in_public_links[]": [],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(criteria_responses.count(), 3)

        c1 = fetch_fresh(c1)
        self.assertEqual(c1.answer, "2")

        c2 = fetch_fresh(c2)
        self.assertEqual(c2.answer, "3")

        c3 = fetch_fresh(c3)
        self.assertEqual(c3.answer, "1,2,3")
