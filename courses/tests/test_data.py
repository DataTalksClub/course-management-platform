from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Enrollment,
    Question,
    QuestionTypes,
    HomeworkState,
    Answer,
    Project,
    ProjectSubmission,
)

from accounts.models import CustomUser, Token

from .util import join_possible_answers


class DataAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser", password="password"
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

    def test_homework_data_view(self):
        self.homework = Homework.objects.create(
            course=self.course,
            title="Test Homework",
            description="Test Homework Description",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.OPEN.value,
            slug="test-homework",
        )

        self.submission = Submission.objects.create(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
            homework_link="https://example.com/homework",
        )

        self.question = Question.objects.create(
            homework=self.homework,
            text="What is the capital of France?",
            question_type=QuestionTypes.MULTIPLE_CHOICE.value,
            possible_answers=join_possible_answers(
                ["Paris", "London", "Berlin"]
            ),
            correct_answer="1",
        )
        self.question.save()

        self.answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            answer_text="1",
            is_correct=True,
        )

        url = reverse(
            "data_homework",
            kwargs={
                "course_slug": self.course.slug,
                "homework_slug": self.homework.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()

        # Test course fields
        self.assertEqual(actual_result["course"]["id"], self.course.id)
        self.assertEqual(
            actual_result["course"]["slug"], self.course.slug
        )
        self.assertEqual(
            actual_result["course"]["title"], self.course.title
        )
        self.assertEqual(
            actual_result["course"]["description"],
            self.course.description,
        )
        self.assertEqual(
            actual_result["course"]["social_media_hashtag"],
            self.course.social_media_hashtag,
        )
        self.assertEqual(
            actual_result["course"]["faq_document_url"],
            self.course.faq_document_url,
        )

        # Test homework fields
        self.assertEqual(
            actual_result["homework"]["id"], self.homework.id
        )
        self.assertEqual(
            actual_result["homework"]["slug"], self.homework.slug
        )
        self.assertEqual(
            actual_result["homework"]["course"], self.course.id
        )
        self.assertEqual(
            actual_result["homework"]["title"], self.homework.title
        )
        self.assertEqual(
            actual_result["homework"]["description"],
            self.homework.description,
        )
        # self.assertEqual(
        #     actual_result["homework"]["due_date"],
        #     "2024-07-18T17:03:14.959Z",
        # )
        self.assertEqual(
            actual_result["homework"]["learning_in_public_cap"],
            self.homework.learning_in_public_cap,
        )
        self.assertEqual(
            actual_result["homework"]["homework_url_field"],
            self.homework.homework_url_field,
        )
        self.assertEqual(
            actual_result["homework"]["time_spent_lectures_field"],
            self.homework.time_spent_lectures_field,
        )
        self.assertEqual(
            actual_result["homework"]["time_spent_homework_field"],
            self.homework.time_spent_homework_field,
        )
        self.assertEqual(
            actual_result["homework"]["problems_comments_field"],
            self.homework.problems_comments_field,
        )
        self.assertEqual(
            actual_result["homework"]["faq_contribution_field"],
            self.homework.faq_contribution_field,
        )
        self.assertEqual(
            actual_result["homework"]["state"], self.homework.state
        )

        # Test submissions fields
        self.assertEqual(len(actual_result["submissions"]), 1)
        submission = actual_result["submissions"][0]
        self.assertEqual(submission["student_id"], self.user.id)
        self.assertEqual(
            submission["homework_link"], self.submission.homework_link
        )
        self.assertEqual(
            submission["learning_in_public_links"],
            self.submission.learning_in_public_links,
        )
        self.assertEqual(
            submission["time_spent_lectures"],
            self.submission.time_spent_lectures,
        )
        self.assertEqual(
            submission["time_spent_homework"],
            self.submission.time_spent_homework,
        )
        self.assertEqual(
            submission["problems_comments"],
            self.submission.problems_comments,
        )
        self.assertEqual(
            submission["faq_contribution"],
            self.submission.faq_contribution,
        )
        self.assertEqual(
            submission["questions_score"],
            self.submission.questions_score,
        )
        self.assertEqual(
            submission["faq_score"], self.submission.faq_score
        )
        self.assertEqual(
            submission["learning_in_public_score"],
            self.submission.learning_in_public_score,
        )
        self.assertEqual(
            submission["total_score"], self.submission.total_score
        )

        # Test answers fields
        self.assertEqual(len(submission["answers"]), 1)

        answer = submission["answers"][0]
        self.assertEqual(answer["question_id"], self.question.id)
        self.assertEqual(answer["answer_text"], self.answer.answer_text)
        self.assertEqual(answer["is_correct"], True)

    def test_project_data_view(self):
        self.project = Project.objects.create(
            course=self.course,
            slug="test-project",
            title="Test Project",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

        self.project_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/repo",
            commit_id="abcd1234",
        )

        url = reverse(
            "data_project",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        actual_result = response.json()
        
        
        # Expected results
        expected_course = {
            "id": self.course.id,
            "slug": self.course.slug,
            "title": self.course.title,
            "description": self.course.description,
            "social_media_hashtag": self.course.social_media_hashtag,
            "faq_document_url": self.course.faq_document_url,
        }

        expected_project = {
            "id": self.project.id,
            "course": self.course.id,
            "slug": self.project.slug,
            "title": self.project.title,
            "description": self.project.description,
            "learning_in_public_cap_project": self.project.learning_in_public_cap_project,
            "time_spent_project_field": self.project.time_spent_project_field,
            "problems_comments_field": self.project.problems_comments_field,
            "faq_contribution_field": self.project.faq_contribution_field,
            "learning_in_public_cap_review": self.project.learning_in_public_cap_review,
            "number_of_peers_to_evaluate": self.project.number_of_peers_to_evaluate,
            "points_for_peer_review": self.project.points_for_peer_review,
            "time_spent_evaluation_field": self.project.time_spent_evaluation_field,
            "points_to_pass": self.project.points_to_pass,
            "state": self.project.state,
        }

        expected_submission = {
            "student_id": self.user.id,
            "github_link": self.project_submission.github_link,
            "commit_id": self.project_submission.commit_id,
            "learning_in_public_links": self.project_submission.learning_in_public_links,
            "faq_contribution": self.project_submission.faq_contribution,
            "time_spent": self.project_submission.time_spent,
            "problems_comments": self.project_submission.problems_comments,
            "project_score": self.project_submission.project_score,
            "project_faq_score": self.project_submission.project_faq_score,
            "project_learning_in_public_score": self.project_submission.project_learning_in_public_score,
            "peer_review_score": self.project_submission.peer_review_score,
            "peer_review_learning_in_public_score": self.project_submission.peer_review_learning_in_public_score,
            "total_score": self.project_submission.total_score,
            "reviewed_enough_peers": self.project_submission.reviewed_enough_peers,
            "passed": self.project_submission.passed,
        }

        # Compare course fields
        self.assertEqual(actual_result['course']['id'], expected_course['id'])
        self.assertEqual(actual_result['course']['slug'], expected_course['slug'])
        self.assertEqual(actual_result['course']['title'], expected_course['title'])
        self.assertEqual(actual_result['course']['description'], expected_course['description'])
        self.assertEqual(actual_result['course']['social_media_hashtag'], expected_course['social_media_hashtag'])
        self.assertEqual(actual_result['course']['faq_document_url'], expected_course['faq_document_url'])
        
        # Compare project fields
        self.assertEqual(actual_result['project']['id'], expected_project['id'])
        self.assertEqual(actual_result['project']['course'], expected_project['course'])
        self.assertEqual(actual_result['project']['slug'], expected_project['slug'])
        self.assertEqual(actual_result['project']['title'], expected_project['title'])
        self.assertEqual(actual_result['project']['description'], expected_project['description'])
        self.assertEqual(actual_result['project']['learning_in_public_cap_project'], expected_project['learning_in_public_cap_project'])
        self.assertEqual(actual_result['project']['time_spent_project_field'], expected_project['time_spent_project_field'])
        self.assertEqual(actual_result['project']['problems_comments_field'], expected_project['problems_comments_field'])
        self.assertEqual(actual_result['project']['faq_contribution_field'], expected_project['faq_contribution_field'])
        self.assertEqual(actual_result['project']['learning_in_public_cap_review'], expected_project['learning_in_public_cap_review'])
        self.assertEqual(actual_result['project']['number_of_peers_to_evaluate'], expected_project['number_of_peers_to_evaluate'])
        self.assertEqual(actual_result['project']['points_for_peer_review'], expected_project['points_for_peer_review'])
        self.assertEqual(actual_result['project']['time_spent_evaluation_field'], expected_project['time_spent_evaluation_field'])
        self.assertEqual(actual_result['project']['points_to_pass'], expected_project['points_to_pass'])
        self.assertEqual(actual_result['project']['state'], expected_project['state'])

        # Compare submissions fields
        self.assertEqual(len(actual_result['submissions']), 1)
        submission = actual_result['submissions'][0]
        self.assertEqual(submission['student_id'], expected_submission['student_id'])
        self.assertEqual(submission['github_link'], expected_submission['github_link'])
        self.assertEqual(submission['commit_id'], expected_submission['commit_id'])
        self.assertEqual(submission['learning_in_public_links'], expected_submission['learning_in_public_links'])
        self.assertEqual(submission['faq_contribution'], expected_submission['faq_contribution'])
        self.assertEqual(submission['time_spent'], expected_submission['time_spent'])
        self.assertEqual(submission['problems_comments'], expected_submission['problems_comments'])
        self.assertEqual(submission['project_score'], expected_submission['project_score'])
        self.assertEqual(submission['project_faq_score'], expected_submission['project_faq_score'])
        self.assertEqual(submission['project_learning_in_public_score'], expected_submission['project_learning_in_public_score'])
        self.assertEqual(submission['peer_review_score'], expected_submission['peer_review_score'])
        self.assertEqual(submission['peer_review_learning_in_public_score'], expected_submission['peer_review_learning_in_public_score'])
        self.assertEqual(submission['total_score'], expected_submission['total_score'])
        self.assertEqual(submission['reviewed_enough_peers'], expected_submission['reviewed_enough_peers'])
        self.assertEqual(submission['passed'], expected_submission['passed'])
