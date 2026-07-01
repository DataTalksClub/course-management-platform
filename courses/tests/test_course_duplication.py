from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    ReviewCriteria,
    ReviewCriteriaTypes,
    User,
)


class CourseDuplicationTests(TestCase):
    def create_course(self):
        return Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test course description",
        )

    def setUp(self):
        self.course = self.create_course()

    def create_code_quality_criteria(self):
        options = [
            {"criteria": "Poor", "score": 0},
            {"criteria": "Good", "score": 1},
            {"criteria": "Excellent", "score": 2},
        ]
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            options=options,
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )

    def create_features_criteria(self):
        options = [
            {"criteria": "Basic Features", "score": 1},
            {"criteria": "Advanced Features", "score": 2},
        ]
        return ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            options=options,
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def create_admin_client(self):
        User.objects.create_superuser(
            username="admin@test.com",
            email="admin@test.com",
            password="admin12345",
        )
        admin_client = Client()
        admin_client.login(
            username="admin@test.com", password="admin12345"
        )
        return admin_client

    def prepare_course_for_duplication(self, year):
        self.course.title = f"Test Course {year - 1}"
        self.course.slug = f"test-course-{year - 1}"
        self.course.social_media_hashtag = "#testcourse2023"
        self.course.faq_document_url = "https://example.com/faq"
        self.course.project_passing_score = 75
        self.course.save()

    def prepare_hidden_course_for_duplication(self, year):
        self.prepare_course_for_duplication(year)
        self.course.visible = False
        self.course.save(update_fields=["visible"])

    def duplicate_course(self, admin_client):
        url = reverse("admin:courses_course_changelist")
        data = {
            "action": "duplicate_course",
            "_selected_action": [str(self.course.pk)],
        }
        return admin_client.post(url, data, follow=True)

    def duplicated_course(self, year):
        return Course.objects.get(slug=f"test-course-{year}")

    def assert_duplicated_course_fields(self, new_course, year):
        self.assertEqual(new_course.title, f"Test Course {year}")
        self.assertEqual(new_course.description, self.course.description)
        self.assertEqual(
            new_course.social_media_hashtag,
            self.course.social_media_hashtag,
        )
        self.assertEqual(
            new_course.faq_document_url, self.course.faq_document_url
        )
        self.assertEqual(
            new_course.project_passing_score,
            self.course.project_passing_score,
        )
        self.assertFalse(new_course.first_homework_scored)
        self.assertFalse(new_course.finished)

    def assert_duplicated_criteria(
        self, new_course, review_criteria1, review_criteria2
    ):
        new_criteria = new_course.reviewcriteria_set.all()
        new_criteria_count = new_criteria.count()
        self.assertEqual(new_criteria_count, 2)
        criteria1 = new_criteria.get(description="Code Quality")
        self.assertEqual(criteria1.options, review_criteria1.options)
        self.assertEqual(
            criteria1.review_criteria_type,
            ReviewCriteriaTypes.RADIO_BUTTONS.value,
        )
        criteria2 = new_criteria.get(description="Features Implemented")
        self.assertEqual(criteria2.options, review_criteria2.options)
        self.assertEqual(
            criteria2.review_criteria_type,
            ReviewCriteriaTypes.CHECKBOXES.value,
        )

    def test_duplicate_course(self):
        review_criteria1 = self.create_code_quality_criteria()
        review_criteria2 = self.create_features_criteria()
        admin_client = self.create_admin_client()
        current_year = timezone.now().year
        self.prepare_course_for_duplication(current_year)

        response = self.duplicate_course(admin_client)

        self.assertEqual(response.status_code, 200)
        new_course = self.duplicated_course(current_year)
        self.assert_duplicated_course_fields(new_course, current_year)
        self.assert_duplicated_criteria(
            new_course, review_criteria1, review_criteria2
        )
        student_count = new_course.students.count()
        self.assertEqual(student_count, 0)

    def test_duplicate_course_preserves_visibility(self):
        current_year = timezone.now().year
        self.prepare_hidden_course_for_duplication(current_year)
        admin_client = self.create_admin_client()

        response = self.duplicate_course(admin_client)

        self.assertEqual(response.status_code, 200)
        new_course = self.duplicated_course(current_year)
        self.assertFalse(new_course.visible)
