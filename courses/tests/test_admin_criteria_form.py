from django.test import TestCase
from django.core.exceptions import ValidationError

from courses.models import Course, ReviewCriteria, ReviewCriteriaTypes
from courses.admin.course import CriteriaForm


class CriteriaFormValidationTestCase(TestCase):
    """Test cases for CriteriaForm validation in the admin panel."""

    def setUp(self):
        """Set up test course for form validation."""
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course"
        )

    def test_form_valid_with_correct_json(self):
        """Test that form is valid with correct JSON structure."""
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': [
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2}
            ]
        }
        form = CriteriaForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form should be valid but has errors: {form.errors}")

    def test_form_invalid_with_dict_instead_of_list(self):
        """Test that form rejects the problematic JSON from the issue."""
        # The exact problematic JSON from the issue
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': {
                "type": "radio",
                "options": [
                    {"score": 0, "criteria": "Project cannot be run with the provided instructions"},
                    {"score": 1, "criteria": "Project can be run, but setup or run instructions are incomplete"},
                    {"score": 2, "criteria": "Clear instructions exist to set up, run, test, and deploy the system end-to-end"}
                ]
            }
        }
        form = CriteriaForm(data=form_data)
        self.assertFalse(form.is_valid(), "Form should be invalid with dict instead of list")
        self.assertIn('options', form.errors)
        self.assertIn('must be a list', str(form.errors['options']))

    def test_form_invalid_with_missing_criteria_key(self):
        """Test that form rejects options missing 'criteria' key."""
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': [
                {"score": 0},
                {"score": 1}
            ]
        }
        form = CriteriaForm(data=form_data)
        self.assertFalse(form.is_valid(), "Form should be invalid with missing 'criteria' key")
        self.assertIn('options', form.errors)
        self.assertIn('criteria', str(form.errors['options']))

    def test_form_invalid_with_missing_score_key(self):
        """Test that form rejects options missing 'score' key."""
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': [
                {"criteria": "Poor"},
                {"criteria": "Good"}
            ]
        }
        form = CriteriaForm(data=form_data)
        self.assertFalse(form.is_valid(), "Form should be invalid with missing 'score' key")
        self.assertIn('options', form.errors)
        self.assertIn('score', str(form.errors['options']))

    def test_form_invalid_with_wrong_score_type(self):
        """Test that form rejects non-integer score values."""
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': [
                {"criteria": "Poor", "score": "0"},  # String instead of int
                {"criteria": "Good", "score": "1"}
            ]
        }
        form = CriteriaForm(data=form_data)
        self.assertFalse(form.is_valid(), "Form should be invalid with string score")
        self.assertIn('options', form.errors)

    def test_form_can_save_valid_criteria(self):
        """Test that valid criteria can be saved through the form."""
        form_data = {
            'course': self.course.id,
            'description': 'Test Criteria',
            'review_criteria_type': ReviewCriteriaTypes.RADIO_BUTTONS.value,
            'options': [
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2}
            ]
        }
        form = CriteriaForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form should be valid but has errors: {form.errors}")
        
        # Save and verify
        criteria = form.save()
        self.assertIsNotNone(criteria.id)
        self.assertEqual(criteria.description, 'Test Criteria')
        self.assertEqual(len(criteria.options), 3)
        self.assertEqual(criteria.options[0]['criteria'], "Poor")
        self.assertEqual(criteria.options[0]['score'], 0)
