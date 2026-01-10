import json
import random
import yaml

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone


from courses.models import (
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
    ReviewCriteria,
    ReviewCriteriaTypes,
)

from accounts.models import CustomUser, Token

from .util import join_possible_answers
from courses.views.data import get_passed_enrollments


class DataAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
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

        self.submission = Submission(
            homework=self.homework,
            student=self.user,
            enrollment=self.enrollment,
            homework_link="https://github.com/DataTalksClub",
        )

        self.submission.save()

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

        self.project_submission = ProjectSubmission(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/DataTalksClub",
            commit_id="abcd1234",
        )

        self.project_submission.save()

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
            "student_email": self.user.email,
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
        self.assertEqual(
            actual_result["course"]["id"], expected_course["id"]
        )
        self.assertEqual(
            actual_result["course"]["slug"], expected_course["slug"]
        )
        self.assertEqual(
            actual_result["course"]["title"], expected_course["title"]
        )
        self.assertEqual(
            actual_result["course"]["description"],
            expected_course["description"],
        )
        self.assertEqual(
            actual_result["course"]["social_media_hashtag"],
            expected_course["social_media_hashtag"],
        )
        self.assertEqual(
            actual_result["course"]["faq_document_url"],
            expected_course["faq_document_url"],
        )

        # Compare project fields
        self.assertEqual(
            actual_result["project"]["id"], expected_project["id"]
        )
        self.assertEqual(
            actual_result["project"]["course"],
            expected_project["course"],
        )
        self.assertEqual(
            actual_result["project"]["slug"], expected_project["slug"]
        )
        self.assertEqual(
            actual_result["project"]["title"], expected_project["title"]
        )
        self.assertEqual(
            actual_result["project"]["description"],
            expected_project["description"],
        )
        self.assertEqual(
            actual_result["project"]["learning_in_public_cap_project"],
            expected_project["learning_in_public_cap_project"],
        )
        self.assertEqual(
            actual_result["project"]["time_spent_project_field"],
            expected_project["time_spent_project_field"],
        )
        self.assertEqual(
            actual_result["project"]["problems_comments_field"],
            expected_project["problems_comments_field"],
        )
        self.assertEqual(
            actual_result["project"]["faq_contribution_field"],
            expected_project["faq_contribution_field"],
        )
        self.assertEqual(
            actual_result["project"]["learning_in_public_cap_review"],
            expected_project["learning_in_public_cap_review"],
        )
        self.assertEqual(
            actual_result["project"]["number_of_peers_to_evaluate"],
            expected_project["number_of_peers_to_evaluate"],
        )
        self.assertEqual(
            actual_result["project"]["points_for_peer_review"],
            expected_project["points_for_peer_review"],
        )
        self.assertEqual(
            actual_result["project"]["time_spent_evaluation_field"],
            expected_project["time_spent_evaluation_field"],
        )
        self.assertEqual(
            actual_result["project"]["points_to_pass"],
            expected_project["points_to_pass"],
        )
        self.assertEqual(
            actual_result["project"]["state"], expected_project["state"]
        )

        # Compare submissions fields
        self.assertEqual(len(actual_result["submissions"]), 1)
        submission = actual_result["submissions"][0]
        self.assertEqual(
            submission["student_id"], expected_submission["student_id"]
        )
        self.assertEqual(
            submission["student_email"],
            expected_submission["student_email"],
        )
        self.assertEqual(
            submission["github_link"],
            expected_submission["github_link"],
        )
        self.assertEqual(
            submission["commit_id"], expected_submission["commit_id"]
        )
        self.assertEqual(
            submission["learning_in_public_links"],
            expected_submission["learning_in_public_links"],
        )
        self.assertEqual(
            submission["faq_contribution"],
            expected_submission["faq_contribution"],
        )
        self.assertEqual(
            submission["time_spent"], expected_submission["time_spent"]
        )
        self.assertEqual(
            submission["problems_comments"],
            expected_submission["problems_comments"],
        )
        self.assertEqual(
            submission["project_score"],
            expected_submission["project_score"],
        )
        self.assertEqual(
            submission["project_faq_score"],
            expected_submission["project_faq_score"],
        )
        self.assertEqual(
            submission["project_learning_in_public_score"],
            expected_submission["project_learning_in_public_score"],
        )
        self.assertEqual(
            submission["peer_review_score"],
            expected_submission["peer_review_score"],
        )
        self.assertEqual(
            submission["peer_review_learning_in_public_score"],
            expected_submission["peer_review_learning_in_public_score"],
        )
        self.assertEqual(
            submission["total_score"],
            expected_submission["total_score"],
        )
        self.assertEqual(
            submission["reviewed_enough_peers"],
            expected_submission["reviewed_enough_peers"],
        )
        self.assertEqual(
            submission["passed"], expected_submission["passed"]
        )

    def test_graduate_data_view(self):
        """Test that only students who passed enough projects are returned."""

        self.course.min_projects_to_pass = 2
        self.course.save()

        self.user.email = "student1@example.com"
        self.user.save()
        self.enrollment.certificate_name = "Student One"
        self.enrollment.save()

        other_user = CustomUser.objects.create(
            username="student2",
            email="student2@example.com",
            password="pass",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
            certificate_name="Student Two",
        )

        project1 = Project.objects.create(
            course=self.course,
            slug="project1",
            title="Project 1",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )
        project2 = Project.objects.create(
            course=self.course,
            slug="project2",
            title="Project 2",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

        ProjectSubmission.objects.create(
            project=project1,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="1111",
            passed=True,
        )
        ProjectSubmission.objects.create(
            project=project2,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="2222",
            passed=True,
        )
        ProjectSubmission.objects.create(
            project=project1,
            student=other_user,
            enrollment=other_enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="3333",
            passed=True,
        )

        url = reverse(
            "data_graduates",
            kwargs={"course_slug": self.course.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        graduates = response_json["graduates"]

        self.assertEqual(len(graduates), 1)

        first_graduate = graduates[0]
        self.assertEqual(first_graduate["email"], self.user.email)
        self.assertEqual(
            first_graduate["name"], self.enrollment.certificate_name
        )

    def create_test_project(self, slug, title):
        return Project(
            course=self.course,
            slug=slug,
            title=title,
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_project_submission(self, project, student, enrollment):
        commit_id = "".join(random.choices("0123456789abcdef", k=7))

        return ProjectSubmission(
            project=project,
            student=student,
            enrollment=enrollment,
            github_link=f"https://github.com/test{student.username[-1]}",
            commit_id=commit_id,
            passed=True,
        )

    def test_get_passed_enrollments(self):
        """Test the get_passed_enrollments function with various scenarios."""

        # Create additional users and enrollments for testing
        user2 = CustomUser(
            username="student2",
            email="student2@example.com",
        )
        user3 = CustomUser(
            username="student3",
            email="student3@example.com",
        )
        user4 = CustomUser(
            username="student4",
            email="student4@example.com",
        )

        enrollment2 = Enrollment(
            id=2,
            student=user2,
            course=self.course,
        )
        enrollment3 = Enrollment(
            id=3,
            student=user3,
            course=self.course,
        )
        enrollment4 = Enrollment(
            id=4,
            student=user4,
            course=self.course,
        )

        project1 = self.create_test_project("p1", "P1")
        project2 = self.create_test_project("p2", "P2")
        project3 = self.create_test_project("p3", "P3")

        # User 1: Passes 2 projects (should be included with min_projects=2)
        submission1_user1 = self.create_project_submission(
            project1, self.user, self.enrollment
        )
        submission2_user1 = self.create_project_submission(
            project2, self.user, self.enrollment
        )

        # User 2: Passes 1 project (should NOT be included with min_projects=2)
        submission1_user2 = self.create_project_submission(
            project1, user2, enrollment2
        )

        # User 3: Passes 3 projects (should be included with min_projects=2)
        submission1_user3 = self.create_project_submission(
            project1, user3, enrollment3
        )
        submission2_user3 = self.create_project_submission(
            project2, user3, enrollment3
        )
        submission3_user3 = self.create_project_submission(
            project3, user3, enrollment3
        )

        passed_submissions = [
            submission1_user1,
            submission2_user1,
            submission1_user2,
            submission1_user3,
            submission2_user3,
            submission3_user3,
        ]

        # Test with min_projects=2
        result = get_passed_enrollments(passed_submissions, 2)

        # Should return 2 enrollments (user1 with 2 passed, user3 with 3 passed)
        self.assertEqual(len(result), 2)

        # Check that the correct enrollments are returned
        self.assertIn(self.enrollment, result)  # User 1
        self.assertIn(enrollment3, result)  # User 3
        self.assertNotIn(enrollment2, result)  # User 2 (only 1 passed)
        self.assertNotIn(enrollment4, result)  # User 4 (no submissions)

        # Test with min_projects=1
        result = get_passed_enrollments(passed_submissions, 1)

        # Should return 3 enrollments (all users with at least 1 passed)
        self.assertEqual(len(result), 3)

        # Check that the correct enrollments are returned
        self.assertIn(self.enrollment, result)  # User 1
        self.assertIn(enrollment2, result)  # User 2
        self.assertIn(enrollment3, result)  # User 3
        self.assertNotIn(enrollment4, result)  # User 4 (no submissions)

        # Test with min_projects=3
        result = get_passed_enrollments(passed_submissions, 3)

        # Should return 1 enrollment (only user3 with 3 passed)
        self.assertEqual(len(result), 1)

        # Check that only user3's enrollment is returned
        self.assertEqual(result[0], enrollment3)

        # Test with min_projects=4
        result = get_passed_enrollments(passed_submissions, 4)

        # Should return 0 enrollments (no user has 4 passed projects)
        self.assertEqual(len(result), 0)

        # Test with empty submissions list
        result = get_passed_enrollments([], 1)
        self.assertEqual(len(result), 0)

        # Test with min_projects=0
        with self.assertRaises(AssertionError):
            result = get_passed_enrollments(passed_submissions, 0)

    def test_update_enrollment_certificate_view(self):
        """Test updating enrollment certificate URL"""
        url = reverse(
            "data_update_certificate",
            kwargs={"course_slug": self.course.slug},
        )

        # Test successful update
        data = {
            "email": self.user.email,
            "certificate_path": "/certificates/test-certificate.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(
            result["certificate_url"],
            "/certificates/test-certificate.pdf",
        )

        # Verify the enrollment was updated
        self.enrollment.refresh_from_db()
        self.assertEqual(
            self.enrollment.certificate_url,
            "/certificates/test-certificate.pdf",
        )

        # Test missing email
        data = {"certificate_path": "/certificates/test.pdf"}
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Test missing certificate_path
        data = {"email": self.user.email}
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Test non-existent user
        data = {
            "email": "nonexistent@example.com",
            "certificate_path": "/certificates/test.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

        # Test non-enrolled user
        other_user = CustomUser.objects.create(
            username="otheruser",
            email="other@example.com",
            password="password",
        )
        data = {
            "email": other_user.email,
            "certificate_path": "/certificates/test.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

        # Test wrong HTTP method
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_course_criteria_yaml_view(self):
        """Test the course criteria YAML endpoint"""
        # Create some review criteria for the test course
        criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ]
        )
        
        criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
            options=[
                {"criteria": "Basic functionality", "score": 1},
                {"criteria": "Advanced features", "score": 2},
                {"criteria": "Documentation", "score": 1},
            ]
        )
        
        # Test the endpoint
        url = reverse(
            "course_criteria_yaml",
            kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)
        
        # Check response status and content type
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/plain; charset=utf-8")
        
        # Parse and validate YAML content
        yaml_content = response.content.decode('utf-8')
        parsed_data = yaml.safe_load(yaml_content)
        
        # Validate structure
        self.assertIn('course', parsed_data)
        self.assertIn('review_criteria', parsed_data)
        
        # Validate course data
        course_data = parsed_data['course']
        self.assertEqual(course_data['slug'], self.course.slug)
        self.assertEqual(course_data['title'], self.course.title)
        
        # Validate criteria data
        criteria_data = parsed_data['review_criteria']
        self.assertEqual(len(criteria_data), 2)
        
        # Check first criteria (Code Quality)
        first_criteria = criteria_data[0]
        self.assertEqual(first_criteria['description'], 'Code Quality')
        self.assertEqual(first_criteria['type'], 'Radio Buttons')
        self.assertEqual(first_criteria['review_criteria_type'], 'RB')
        self.assertEqual(len(first_criteria['options']), 3)
        self.assertEqual(first_criteria['options'][0]['criteria'], 'Poor')
        self.assertEqual(first_criteria['options'][0]['score'], 0)
        
        # Check second criteria (Features Implemented)
        second_criteria = criteria_data[1]
        self.assertEqual(second_criteria['description'], 'Features Implemented')
        self.assertEqual(second_criteria['type'], 'Checkboxes')
        self.assertEqual(second_criteria['review_criteria_type'], 'CB')
        self.assertEqual(len(second_criteria['options']), 3)
        
    def test_course_criteria_yaml_view_no_criteria(self):
        """Test the endpoint when course has no criteria"""
        # Create a course with no criteria
        empty_course = Course.objects.create(
            title="Empty Course",
            slug="empty-course"
        )
        
        url = reverse(
            "course_criteria_yaml",
            kwargs={"course_slug": empty_course.slug}
        )
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Parse and validate YAML content
        yaml_content = response.content.decode('utf-8')
        parsed_data = yaml.safe_load(yaml_content)
        
        # Should have course data but empty criteria list
        self.assertIn('course', parsed_data)
        self.assertIn('review_criteria', parsed_data)
        self.assertEqual(len(parsed_data['review_criteria']), 0)
        
    def test_course_criteria_yaml_view_nonexistent_course(self):
        """Test the endpoint with non-existent course"""
        url = reverse(
            "course_criteria_yaml",
            kwargs={"course_slug": "nonexistent-course"}
        )
        response = self.client.get(url)
        
        # Should return 404 for non-existent course
        self.assertEqual(response.status_code, 404)
        
    def test_course_criteria_yaml_view_no_auth(self):
        """Test the endpoint without authentication (should work since no auth required)"""
        # Create client without authentication
        unauth_client = Client()
        
        url = reverse(
            "course_criteria_yaml",
            kwargs={"course_slug": self.course.slug}
        )
        response = unauth_client.get(url)

        # Should return 200 since no authentication is required
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/plain; charset=utf-8")


class CreateCourseContentAPITestCase(TestCase):
    """Comprehensive tests for the create_course_content_view endpoint"""

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.url = reverse(
            "data_content",
            kwargs={"course_slug": self.course.slug},
        )

    def test_create_homeworks_only(self):
        """Test creating homeworks without projects"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "slug": "hw-1",
                    "due_date": "2025-03-15T23:59:59Z",
                    "description": "First homework",
                },
                {
                    "name": "Homework 2",
                    "due_date": "2025-03-22T23:59:59Z",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(result["course"], self.course.slug)
        self.assertEqual(len(result["created_homeworks"]), 2)
        self.assertEqual(len(result["created_projects"]), 0)
        self.assertEqual(len(result["errors"]), 0)

        # Verify homeworks were created in DB
        homeworks = Homework.objects.filter(course=self.course)
        self.assertEqual(homeworks.count(), 2)

        hw1 = homeworks.get(slug="hw-1")
        self.assertEqual(hw1.title, "Homework 1")
        self.assertEqual(hw1.state, HomeworkState.CLOSED.value)
        self.assertEqual(hw1.description, "First homework")

        hw2 = homeworks.get(slug="homework-2")
        self.assertEqual(hw2.title, "Homework 2")
        self.assertEqual(hw2.state, HomeworkState.CLOSED.value)

    def test_create_projects_only(self):
        """Test creating projects without homeworks"""
        data = {
            "projects": [
                {
                    "name": "Project 1",
                    "slug": "proj-1",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                    "description": "First project",
                },
                {
                    "name": "Project 2",
                    "submission_due_date": "2025-04-10T23:59:59Z",
                    "peer_review_due_date": "2025-04-17T23:59:59Z",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["created_projects"]), 2)
        self.assertEqual(len(result["errors"]), 0)

        # Verify projects were created in DB
        projects = Project.objects.filter(course=self.course)
        self.assertEqual(projects.count(), 2)

        proj1 = projects.get(slug="proj-1")
        self.assertEqual(proj1.title, "Project 1")
        self.assertEqual(proj1.state, "CL")
        self.assertEqual(proj1.description, "First project")

        proj2 = projects.get(slug="project-2")
        self.assertEqual(proj2.title, "Project 2")
        self.assertEqual(proj2.state, "CL")

    def test_create_both_homeworks_and_projects(self):
        """Test creating both homeworks and projects in one request"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Project 1",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(len(result["created_projects"]), 1)

        # Verify in DB
        self.assertEqual(Homework.objects.filter(course=self.course).count(), 1)
        self.assertEqual(Project.objects.filter(course=self.course).count(), 1)

    def test_create_homework_with_questions(self):
        """Test creating homework with questions"""
        data = {
            "homeworks": [
                {
                    "name": "Homework with Questions",
                    "slug": "hw-questions",
                    "due_date": "2025-03-15T23:59:59Z",
                    "questions": [
                        {
                            "text": "What is 2+2?",
                            "question_type": "MC",
                            "answer_type": "INT",
                            "possible_answers": ["3", "4", "5"],
                            "correct_answer": "2",
                            "scores_for_correct_answer": 1,
                        },
                        {
                            "text": "Explain your answer",
                            "question_type": "FF",
                            "answer_type": "ANY",
                            "scores_for_correct_answer": 2,
                        },
                    ],
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        hw_data = result["created_homeworks"][0]
        self.assertEqual(hw_data["questions_count"], 2)

        # Verify questions in DB
        homework = Homework.objects.get(slug="hw-questions")
        questions = homework.question_set.all()
        self.assertEqual(questions.count(), 2)

        q1 = questions[0]
        self.assertEqual(q1.text, "What is 2+2?")
        self.assertEqual(q1.question_type, "MC")
        self.assertEqual(q1.possible_answers, "3\n4\n5")
        self.assertEqual(q1.correct_answer, "2")
        self.assertEqual(q1.scores_for_correct_answer, 1)

        q2 = questions[1]
        self.assertEqual(q2.text, "Explain your answer")
        self.assertEqual(q2.question_type, "FF")
        self.assertEqual(q2.answer_type, "ANY")

    def test_homework_without_questions(self):
        """Test creating homework without questions (questions are optional)"""
        data = {
            "homeworks": [
                {
                    "name": "Homework No Questions",
                    "slug": "hw-no-questions",
                    "due_date": "2025-03-15T23:59:59Z",
                    "description": "Homework without any questions",
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        hw_data = result["created_homeworks"][0]
        self.assertEqual(hw_data["questions_count"], 0)

        # Verify homework was created with no questions in DB
        homework = Homework.objects.get(slug="hw-no-questions")
        self.assertEqual(homework.title, "Homework No Questions")
        self.assertEqual(homework.description, "Homework without any questions")
        self.assertEqual(homework.question_set.count(), 0)

    def test_all_question_types(self):
        """Test creating questions with all question types"""
        data = {
            "homeworks": [
                {
                    "name": "All Question Types",
                    "due_date": "2025-03-15T23:59:59Z",
                    "questions": [
                        {
                            "text": "Multiple choice",
                            "question_type": "MC",
                            "possible_answers": ["A", "B", "C"],
                            "correct_answer": "1",
                        },
                        {
                            "text": "Free form",
                            "question_type": "FF",
                        },
                        {
                            "text": "Free form long",
                            "question_type": "FL",
                        },
                        {
                            "text": "Checkboxes",
                            "question_type": "CB",
                            "possible_answers": ["X", "Y", "Z"],
                            "correct_answer": "1,2",
                        },
                    ],
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(result["created_homeworks"][0]["questions_count"], 4)

        homework = Homework.objects.get(slug="all-question-types")
        self.assertEqual(homework.question_set.count(), 4)

    def test_all_answer_types(self):
        """Test creating questions with all answer types"""
        data = {
            "homeworks": [
                {
                    "name": "All Answer Types",
                    "due_date": "2025-03-15T23:59:59Z",
                    "questions": [
                        {
                            "text": "Any answer",
                            "answer_type": "ANY",
                        },
                        {
                            "text": "Float answer",
                            "answer_type": "FLT",
                        },
                        {
                            "text": "Integer answer",
                            "answer_type": "INT",
                        },
                        {
                            "text": "Exact string",
                            "answer_type": "EXS",
                            "correct_answer": "exact",
                        },
                        {
                            "text": "Contains string",
                            "answer_type": "CTS",
                            "correct_answer": "keyword",
                        },
                    ],
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        homework = Homework.objects.get(slug="all-answer-types")
        self.assertEqual(homework.question_set.count(), 5)

    def test_slug_generation(self):
        """Test automatic slug generation from names"""
        data = {
            "homeworks": [
                {
                    "name": "Complex Name With Spaces!!!",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Project Name @2025",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        homework = Homework.objects.get(title="Complex Name With Spaces!!!")
        self.assertEqual(homework.slug, "complex-name-with-spaces")

        project = Project.objects.get(title="Project Name @2025")
        self.assertEqual(project.slug, "project-name-2025")

    def test_custom_slug(self):
        """Test using custom slug instead of auto-generated"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "slug": "custom-hw-slug",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Project 1",
                    "slug": "custom-proj-slug",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        homework = Homework.objects.get(title="Homework 1")
        self.assertEqual(homework.slug, "custom-hw-slug")

        project = Project.objects.get(title="Project 1")
        self.assertEqual(project.slug, "custom-proj-slug")

    def test_duplicate_slug_error(self):
        """Test error when slug already exists"""
        # Create existing homework
        Homework.objects.create(
            course=self.course,
            slug="existing-hw",
            title="Existing Homework",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.CLOSED.value,
        )

        # Create existing project
        Project.objects.create(
            course=self.course,
            slug="existing-proj",
            title="Existing Project",
            submission_due_date=timezone.now() + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=14),
            state="CL",
        )

        data = {
            "homeworks": [
                {
                    "name": "New Homework",
                    "slug": "existing-hw",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "New Project",
                    "slug": "existing-proj",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["created_projects"]), 0)
        self.assertEqual(len(result["errors"]), 2)

        error_messages = [e["error"] for e in result["errors"]]
        self.assertTrue(any("already exists" in msg for msg in error_messages))

    def test_missing_required_fields_homework(self):
        """Test error when homework missing required fields"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    # missing due_date
                },
                {
                    # missing name
                    "due_date": "2025-03-15T23:59:59Z",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["errors"]), 2)

    def test_missing_required_fields_project(self):
        """Test error when project missing required fields"""
        data = {
            "projects": [
                {
                    "name": "Project 1",
                    # missing submission_due_date and peer_review_due_date
                },
                {
                    "name": "Project 2",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    # missing peer_review_due_date
                },
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_projects"]), 0)
        self.assertEqual(len(result["errors"]), 2)

    def test_invalid_date_format(self):
        """Test error with invalid date format"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "invalid-date",
                }
            ],
            "projects": [
                {
                    "name": "Project 1",
                    "submission_due_date": "not-a-date",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["created_projects"]), 0)
        self.assertEqual(len(result["errors"]), 2)

        for error in result["errors"]:
            self.assertTrue("invalid" in error["error"].lower() and "date" in error["error"].lower())

    def test_multiple_date_formats(self):
        """Test different valid date formats"""
        data = {
            "homeworks": [
                {
                    "name": "HW ISO Format",
                    "due_date": "2025-03-15T23:59:59+00:00",
                },
                {
                    "name": "HW Z Format",
                    "due_date": "2025-03-15T23:59:59Z",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 2)
        self.assertEqual(len(result["errors"]), 0)

    def test_nonexistent_course(self):
        """Test with non-existent course"""
        url = reverse(
            "data_content",
            kwargs={"course_slug": "nonexistent-course"},
        )

        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ]
        }

        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 404)

    def test_no_authentication(self):
        """Test that authentication is required"""
        unauth_client = Client()
        # Remove the authorization header

        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ]
        }

        response = unauth_client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        """Test with invalid authentication token"""
        invalid_client = Client()
        invalid_client.defaults["HTTP_AUTHORIZATION"] = "Token invalidtoken123"

        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ]
        }

        response = invalid_client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 401)

    def test_wrong_http_method(self):
        """Test that only GET and POST are allowed"""
        # GET should work
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        # PUT should not work
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, 405)

        # DELETE should not work
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 405)

    def test_get_endpoint_returns_all_content(self):
        """Test GET request returns all homeworks and projects"""
        # Create some homeworks and projects first
        Homework.objects.create(
            course=self.course,
            slug="existing-hw",
            title="Existing Homework",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.CLOSED.value,
        )
        Project.objects.create(
            course=self.course,
            slug="existing-proj",
            title="Existing Project",
            submission_due_date=timezone.now() + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now() + timezone.timedelta(days=14),
            state="CL",
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(result["course"], self.course.slug)
        self.assertIn("homeworks", result)
        self.assertIn("projects", result)

        # Should have the existing homework
        self.assertEqual(len(result["homeworks"]), 1)
        hw = result["homeworks"][0]
        self.assertEqual(hw["slug"], "existing-hw")
        self.assertEqual(hw["title"], "Existing Homework")
        self.assertEqual(hw["state"], HomeworkState.CLOSED.value)
        self.assertIn("id", hw)
        self.assertIn("due_date", hw)
        self.assertIn("questions_count", hw)

        # Should have the existing project
        self.assertEqual(len(result["projects"]), 1)
        proj = result["projects"][0]
        self.assertEqual(proj["slug"], "existing-proj")
        self.assertEqual(proj["title"], "Existing Project")
        self.assertEqual(proj["state"], "CL")
        self.assertIn("id", proj)
        self.assertIn("submission_due_date", proj)
        self.assertIn("peer_review_due_date", proj)

    def test_get_endpoint_empty_course(self):
        """Test GET request for course with no content"""
        # Ensure no homeworks or projects
        Homework.objects.filter(course=self.course).delete()
        Project.objects.filter(course=self.course).delete()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["homeworks"]), 0)
        self.assertEqual(len(result["projects"]), 0)

    def test_get_then_post(self):
        """Test GET after POST returns newly created content"""
        # First, create content via POST
        data = {
            "homeworks": [
                {"name": "New Homework", "slug": "new-hw", "due_date": "2025-03-15T23:59:59Z"}
            ],
            "projects": [
                {
                    "name": "New Project",
                    "slug": "new-proj",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z"
                }
            ]
        }

        post_response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(post_response.status_code, 200)

        # Now GET to verify content was created
        get_response = self.client.get(self.url)
        self.assertEqual(get_response.status_code, 200)
        result = get_response.json()

        self.assertEqual(len(result["homeworks"]), 1)
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["homeworks"][0]["slug"], "new-hw")
        self.assertEqual(result["projects"][0]["slug"], "new-proj")

    def test_invalid_json(self):
        """Test with invalid JSON payload"""
        response = self.client.post(
            self.url, "invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)

    def test_empty_payload(self):
        """Test with empty payload"""
        data = {}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["created_projects"]), 0)
        self.assertEqual(len(result["errors"]), 0)

    def test_empty_arrays(self):
        """Test with empty homeworks and projects arrays"""
        data = {
            "homeworks": [],
            "projects": []
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_homeworks"]), 0)
        self.assertEqual(len(result["created_projects"]), 0)

    def test_all_homeworks_are_closed(self):
        """Test that all created homeworks have CLOSED state"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "due_date": "2025-03-15T23:59:59Z",
                },
                {
                    "name": "Homework 2",
                    "due_date": "2025-03-22T23:59:59Z",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        homeworks = Homework.objects.filter(course=self.course)
        for hw in homeworks:
            self.assertEqual(hw.state, HomeworkState.CLOSED.value)

    def test_all_projects_are_closed(self):
        """Test that all created projects have CLOSED state"""
        data = {
            "projects": [
                {
                    "name": "Project 1",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        projects = Project.objects.filter(course=self.course)
        for proj in projects:
            self.assertEqual(proj.state, "CL")

    def test_question_error_doesnt_prevent_homework_creation(self):
        """Test that errors in question creation don't prevent homework creation"""
        data = {
            "homeworks": [
                {
                    "name": "Homework with Good Questions",
                    "due_date": "2025-03-15T23:59:59Z",
                    "questions": [
                        {
                            "text": "Valid question",
                            "question_type": "FF",
                        }
                    ],
                },
                {
                    "name": "Homework with Bad Questions",
                    "due_date": "2025-03-22T23:59:59Z",
                    "questions": [
                        {
                            # Missing required 'text' field - will create with empty text
                            "question_type": "MC",
                        }
                    ],
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Both homeworks should be created
        self.assertEqual(len(result["created_homeworks"]), 2)

    def test_response_structure(self):
        """Test the structure of the response"""
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "slug": "hw-1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Project 1",
                    "slug": "proj-1",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Check top-level structure
        self.assertIn("success", result)
        self.assertIn("course", result)
        self.assertIn("created_homeworks", result)
        self.assertIn("created_projects", result)
        self.assertIn("errors", result)

        # Check homework structure
        hw = result["created_homeworks"][0]
        self.assertIn("id", hw)
        self.assertIn("slug", hw)
        self.assertIn("title", hw)
        self.assertIn("due_date", hw)
        self.assertIn("state", hw)
        self.assertIn("questions_count", hw)
        self.assertEqual(hw["state"], "CL")

        # Check project structure
        proj = result["created_projects"][0]
        self.assertIn("id", proj)
        self.assertIn("slug", proj)
        self.assertIn("title", proj)
        self.assertIn("submission_due_date", proj)
        self.assertIn("peer_review_due_date", proj)
        self.assertIn("state", proj)
        self.assertEqual(proj["state"], "CL")

    def test_partial_success_with_errors(self):
        """Test that partial success is handled correctly"""
        # Create an existing homework to cause a conflict
        Homework.objects.create(
            course=self.course,
            slug="existing-hw",
            title="Existing",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.CLOSED.value,
        )

        data = {
            "homeworks": [
                {
                    "name": "Valid Homework",
                    "slug": "valid-hw",
                    "due_date": "2025-03-15T23:59:59Z",
                },
                {
                    "name": "Duplicate Slug",
                    "slug": "existing-hw",
                    "due_date": "2025-03-22T23:59:59Z",
                },
                {
                    # Missing due_date
                    "name": "Invalid Homework",
                },
            ],
            "projects": [
                {
                    "name": "Valid Project",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Success is still true overall
        self.assertTrue(result["success"])

        # Only valid homework and project should be created
        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(len(result["created_projects"]), 1)

        # Should have errors for the invalid ones
        self.assertGreater(len(result["errors"]), 0)

    def test_multiple_courses_independent(self):
        """Test that different courses have independent slugs"""
        other_course = Course.objects.create(
            title="Other Course", slug="other-course"
        )

        # Create homework with same slug in other course
        Homework.objects.create(
            course=other_course,
            slug="hw-1",
            title="Other Course Homework",
            due_date=timezone.now() + timezone.timedelta(days=7),
            state=HomeworkState.CLOSED.value,
        )

        # Should be able to create same slug in this course
        data = {
            "homeworks": [
                {
                    "name": "Homework 1",
                    "slug": "hw-1",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(len(result["errors"]), 0)

        # Both courses should have hw-1
        self.assertEqual(
            Homework.objects.filter(course=self.course, slug="hw-1").count(), 1
        )
        self.assertEqual(
            Homework.objects.filter(course=other_course, slug="hw-1").count(), 1
        )

    def test_checkbox_answer_format(self):
        """Test creating checkbox questions with multiple correct answers"""
        data = {
            "homeworks": [
                {
                    "name": "Checkbox Homework",
                    "due_date": "2025-03-15T23:59:59Z",
                    "questions": [
                        {
                            "text": "Select all that apply",
                            "question_type": "CB",
                            "possible_answers": ["Option A", "Option B", "Option C", "Option D"],
                            "correct_answer": "1,2",  # First and second options (1-based)
                            "scores_for_correct_answer": 3,
                        }
                    ],
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        homework = Homework.objects.get(slug="checkbox-homework")
        question = homework.question_set.first()

        self.assertEqual(question.question_type, "CB")
        self.assertEqual(question.correct_answer, "1,2")
        self.assertEqual(question.scores_for_correct_answer, 3)

    def test_unicode_in_names(self):
        """Test handling of unicode characters in names"""
        data = {
            "homeworks": [
                {
                    "name": "Tëst Hömework Ünicode",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Проект Українською",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(len(result["created_projects"]), 1)

        # Verify titles are preserved and objects exist in DB
        hw = Homework.objects.get(slug="test-homework-unicode")
        self.assertEqual(hw.title, "Tëst Hömework Ünicode")

        # Verify project exists with unicode title
        proj = Project.objects.filter(course=self.course).first()
        self.assertEqual(proj.title, "Проект Українською")

    def test_long_names_descriptions(self):
        """Test handling of very long names and descriptions"""
        long_description = "A" * 1000

        data = {
            "homeworks": [
                {
                    "name": "H" * 200,
                    "due_date": "2025-03-15T23:59:59Z",
                    "description": long_description,
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        homework = Homework.objects.first()
        self.assertEqual(len(homework.title), 200)
        self.assertEqual(len(homework.description), 1000)

    def test_description_fields_are_optional(self):
        """Test that description fields are optional"""
        data = {
            "homeworks": [
                {
                    "name": "Homework No Description",
                    "due_date": "2025-03-15T23:59:59Z",
                }
            ],
            "projects": [
                {
                    "name": "Project No Description",
                    "submission_due_date": "2025-03-20T23:59:59Z",
                    "peer_review_due_date": "2025-03-27T23:59:59Z",
                }
            ],
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_homeworks"]), 1)
        self.assertEqual(len(result["created_projects"]), 1)

        # Verify descriptions are empty strings
        homework = Homework.objects.first()
        self.assertEqual(homework.description, "")

        project = Project.objects.first()
        self.assertEqual(project.description, "")


class HomeworkContentAPITestCase(TestCase):
    """Tests for the homework_content_view endpoint"""

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.homework = Homework.objects.create(
            course=self.course,
            slug="test-homework",
            title="Test Homework",
            description="Test Description",
            due_date="2025-03-15T23:59:59Z",
            state="CL",
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

        self.url = reverse(
            "data_homework_content",
            kwargs={"course_slug": self.course.slug, "homework_slug": self.homework.slug}
        )

    def test_get_homework_content_returns_homework_and_questions(self):
        """Test GET returns homework details and questions"""
        # Create some questions
        Question.objects.create(
            homework=self.homework,
            text="What is 2+2?",
            question_type="MC",
            answer_type="INT",
            possible_answers="3\n4\n5",
            correct_answer="2",
            scores_for_correct_answer=1,
        )
        Question.objects.create(
            homework=self.homework,
            text="Explain your answer",
            question_type="FF",
            answer_type="CTS",
            correct_answer="4",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(result["course"], "test-course")
        self.assertEqual(result["homework"]["slug"], "test-homework")
        self.assertEqual(result["homework"]["title"], "Test Homework")
        self.assertEqual(result["homework"]["description"], "Test Description")
        self.assertEqual(result["homework"]["state"], "CL")
        self.assertEqual(result["homework"]["learning_in_public_cap"], 7)
        self.assertTrue(result["homework"]["homework_url_field"])
        self.assertTrue(result["homework"]["time_spent_lectures_field"])
        self.assertTrue(result["homework"]["time_spent_homework_field"])
        self.assertTrue(result["homework"]["faq_contribution_field"])

        # Check questions
        self.assertEqual(len(result["questions"]), 2)
        self.assertEqual(result["questions"][0]["text"], "What is 2+2?")
        self.assertEqual(result["questions"][0]["question_type"], "MC")
        self.assertEqual(result["questions"][0]["possible_answers"], ["3", "4", "5"])
        self.assertEqual(result["questions"][1]["text"], "Explain your answer")

    def test_get_homework_content_empty_questions(self):
        """Test GET returns empty questions list when no questions exist"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["questions"]), 0)

    def test_post_creates_questions(self):
        """Test POST creates questions for homework"""
        data = {
            "questions": [
                {
                    "text": "What is the capital of France?",
                    "question_type": "MC",
                    "answer_type": "EXS",
                    "possible_answers": ["London", "Paris", "Berlin"],
                    "correct_answer": "2",
                    "scores_for_correct_answer": 2,
                },
                {
                    "text": "Describe Paris",
                    "question_type": "FL",
                    "answer_type": "ANY",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertTrue(result["success"])
        self.assertEqual(len(result["created_questions"]), 2)
        self.assertEqual(result["created_questions"][0]["text"], "What is the capital of France?")
        self.assertEqual(len(result["errors"]), 0)

        # Verify questions were created in DB
        self.assertEqual(Question.objects.count(), 2)

    def test_post_empty_questions_list(self):
        """Test POST with empty questions list"""
        data = {"questions": []}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 0)

    def test_post_no_questions_key(self):
        """Test POST without questions key (defaults to empty list)"""
        data = {}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 0)

    def test_post_all_question_types(self):
        """Test POST with all question types"""
        data = {
            "questions": [
                {
                    "text": "Multiple Choice",
                    "question_type": "MC",
                    "answer_type": "INT",
                    "possible_answers": ["1", "2", "3"],
                    "correct_answer": "1",
                },
                {
                    "text": "Free Form",
                    "question_type": "FF",
                    "answer_type": "CTS",
                    "correct_answer": "answer",
                },
                {
                    "text": "Free Form Long",
                    "question_type": "FL",
                    "answer_type": "ANY",
                },
                {
                    "text": "Checkboxes",
                    "question_type": "CB",
                    "answer_type": "INT",
                    "possible_answers": ["A", "B", "C"],
                    "correct_answer": "1,2",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(len(result["created_questions"]), 4)

        # Verify in DB
        mc_question = Question.objects.get(text="Multiple Choice")
        self.assertEqual(mc_question.question_type, "MC")

        ff_question = Question.objects.get(text="Free Form")
        self.assertEqual(ff_question.question_type, "FF")

        fl_question = Question.objects.get(text="Free Form Long")
        self.assertEqual(fl_question.question_type, "FL")

        cb_question = Question.objects.get(text="Checkboxes")
        self.assertEqual(cb_question.question_type, "CB")

    def test_post_all_answer_types(self):
        """Test POST with all answer types"""
        data = {
            "questions": [
                {"text": "ANY", "question_type": "FF", "answer_type": "ANY"},
                {"text": "FLT", "question_type": "FF", "answer_type": "FLT"},
                {"text": "INT", "question_type": "FF", "answer_type": "INT"},
                {"text": "EXS", "question_type": "FF", "answer_type": "EXS"},
                {"text": "CTS", "question_type": "FF", "answer_type": "CTS"},
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["created_questions"]), 5)

    def test_post_default_values(self):
        """Test POST uses default values for optional fields"""
        data = {
            "questions": [
                {
                    "text": "Minimal question",
                }
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        question = Question.objects.first()
        self.assertEqual(question.text, "Minimal question")
        self.assertEqual(question.question_type, "FF")  # default
        self.assertIsNone(question.answer_type)
        self.assertEqual(question.possible_answers, "")
        self.assertEqual(question.correct_answer, "")
        self.assertEqual(question.scores_for_correct_answer, 1)  # default

    def test_nonexistent_course(self):
        """Test with non-existent course"""
        url = reverse(
            "data_homework_content",
            kwargs={"course_slug": "nonexistent", "homework_slug": "hw"}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertEqual(result["error"], "Course or homework not found")

    def test_nonexistent_homework(self):
        """Test with non-existent homework"""
        url = reverse(
            "data_homework_content",
            kwargs={"course_slug": self.course.slug, "homework_slug": "nonexistent"}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        result = response.json()
        self.assertEqual(result["error"], "Course or homework not found")

    def test_wrong_http_method(self):
        """Test with wrong HTTP method"""
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, 405)

    def test_invalid_json(self):
        """Test POST with invalid JSON"""
        response = self.client.post(
            self.url, "invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertEqual(result["error"], "Invalid JSON")

    def test_no_authentication(self):
        """Test without authentication token"""
        unauth_client = Client()
        response = unauth_client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_post_partial_success(self):
        """Test POST continues even if some questions fail"""
        # This will create questions, some might have validation issues
        # but we're testing the error handling pattern
        data = {
            "questions": [
                {
                    "text": "Valid question",
                    "question_type": "FF",
                },
                {
                    "text": "Another valid question",
                    "question_type": "FL",
                },
            ]
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        # Both should succeed since they're valid
        self.assertEqual(len(result["created_questions"]), 2)
        self.assertEqual(len(result["errors"]), 0)

    def test_post_update_state_from_closed_to_open(self):
        """Test POST updates homework state from closed to open"""
        self.assertEqual(self.homework.state, "CL")

        data = {
            "questions": [
                {"text": "New question", "question_type": "FF"}
            ],
            "state": "OP"
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertIn("homework_state", result)
        self.assertEqual(result["homework_state"]["old"], "CL")
        self.assertEqual(result["homework_state"]["new"], "OP")

        # Verify state was updated in DB
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

    def test_post_update_state_only(self):
        """Test POST can update state without adding questions"""
        self.assertEqual(self.homework.state, "CL")

        data = {"state": "OP"}

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()

        self.assertEqual(result["homework_state"]["old"], "CL")
        self.assertEqual(result["homework_state"]["new"], "OP")
        self.assertEqual(len(result["created_questions"]), 0)

        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

    def test_post_update_state_invalid(self):
        """Test POST with invalid state returns error"""
        data = {
            "questions": [{"text": "Question", "question_type": "FF"}],
            "state": "INVALID"
        }

        response = self.client.post(
            self.url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertIn("Invalid state", result["error"])

    def test_post_update_all_states(self):
        """Test POST can update to all valid states"""
        # CL -> OP
        data = {"state": "OP"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "OP")

        # OP -> SC
        data = {"state": "SC"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "SC")

        # SC -> CL
        data = {"state": "CL"}
        response = self.client.post(self.url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.state, "CL")