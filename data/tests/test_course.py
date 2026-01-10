"""
Tests for course-related data API views.

Tests for course_content_view (create/get homeworks and projects) and course_criteria_yaml_view.
"""

import json
import yaml

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Homework,
    Project,
    Question,
    HomeworkState,
    ReviewCriteria,
    ReviewCriteriaTypes,
)

from accounts.models import CustomUser, Token


class CourseContentAPITestCase(TestCase):
    """Comprehensive tests for the course_content_view endpoint."""

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
        """Test creating homeworks without projects."""
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
        """Test creating projects without homeworks."""
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
        """Test creating both homeworks and projects in one request."""
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
        """Test creating homework with questions."""
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
        """Test creating homework without questions (questions are optional)."""
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
        """Test creating questions with all question types."""
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
        """Test creating questions with all answer types."""
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
        """Test automatic slug generation from names."""
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
        """Test using custom slug instead of auto-generated."""
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
        """Test error when slug already exists."""
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
        """Test error when homework missing required fields."""
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
        """Test error when project missing required fields."""
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
        """Test error with invalid date format."""
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
        """Test different valid date formats."""
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
        """Test with non-existent course."""
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
        """Test that authentication is required."""
        unauth_client = Client()

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
        """Test with invalid authentication token."""
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
        """Test that only GET and POST are allowed."""
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
        """Test GET request returns all homeworks and projects."""
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
        """Test GET request for course with no content."""
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
        """Test GET after POST returns newly created content."""
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
        """Test with invalid JSON payload."""
        response = self.client.post(
            self.url, "invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)

    def test_empty_payload(self):
        """Test with empty payload."""
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
        """Test with empty homeworks and projects arrays."""
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
        """Test that all created homeworks have CLOSED state."""
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
        """Test that all created projects have CLOSED state."""
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
        """Test that errors in question creation don't prevent homework creation."""
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
        """Test the structure of the response."""
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
        """Test that partial success is handled correctly."""
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
        """Test that different courses have independent slugs."""
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
        """Test creating checkbox questions with multiple correct answers."""
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
        """Test handling of unicode characters in names."""
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
        """Test handling of very long names and descriptions."""
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
        """Test that description fields are optional."""
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


class CourseCriteriaYAMLViewTestCase(TestCase):
    """Tests for the course_criteria_yaml_view endpoint."""

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

        # Note: This endpoint doesn't require authentication
        self.client = Client()

    def test_course_criteria_yaml_view(self):
        """Test the course criteria YAML endpoint."""
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
        """Test the endpoint when course has no criteria."""
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
        """Test the endpoint with non-existent course."""
        url = reverse(
            "course_criteria_yaml",
            kwargs={"course_slug": "nonexistent-course"}
        )
        response = self.client.get(url)

        # Should return 404 for non-existent course
        self.assertEqual(response.status_code, 404)

    def test_course_criteria_yaml_view_no_auth(self):
        """Test the endpoint without authentication (should work since no auth required)."""
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
