import logging
from unittest import TestCase
from django.core.exceptions import ValidationError

from courses.validators.criteria_validators import validate_review_criteria_options


logger = logging.getLogger(__name__)


class CriteriaValidationTestCase(TestCase):
    """Test cases for review criteria options validation."""

    def test_valid_options(self):
        """Test that valid options pass validation."""
        valid_options = [
            {"criteria": "Poor", "score": 0},
            {"criteria": "Satisfactory", "score": 1},
            {"criteria": "Good", "score": 2},
            {"criteria": "Excellent", "score": 3},
        ]
        # Should not raise any exception
        validate_review_criteria_options(valid_options)

    def test_invalid_options_not_list(self):
        """Test that non-list options raise ValidationError."""
        # The problematic JSON from the issue
        invalid_options = {
            "type": "radio",
            "options": [
                {"score": 0, "criteria": "Project cannot be run with the provided instructions"},
                {"score": 1, "criteria": "Project can be run, but setup or run instructions are incomplete"},
                {"score": 2, "criteria": "Clear instructions exist to set up, run, test, and deploy the system end-to-end"}
            ]
        }
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("must be a list", str(context.exception))

    def test_empty_list(self):
        """Test that empty list raises ValidationError."""
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options([])
        self.assertIn("cannot be empty", str(context.exception))

    def test_option_not_dict(self):
        """Test that non-dict option raises ValidationError."""
        invalid_options = [
            "Poor",
            "Good",
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("must be a dictionary", str(context.exception))

    def test_missing_criteria_key(self):
        """Test that missing 'criteria' key raises ValidationError."""
        invalid_options = [
            {"score": 0},
            {"score": 1},
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("missing required key 'criteria'", str(context.exception))

    def test_missing_score_key(self):
        """Test that missing 'score' key raises ValidationError."""
        invalid_options = [
            {"criteria": "Poor"},
            {"criteria": "Good"},
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("missing required key 'score'", str(context.exception))

    def test_criteria_not_string(self):
        """Test that non-string criteria raises ValidationError."""
        invalid_options = [
            {"criteria": 123, "score": 0},
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("'criteria' must be a string", str(context.exception))

    def test_score_not_int(self):
        """Test that non-integer score raises ValidationError."""
        invalid_options = [
            {"criteria": "Poor", "score": "0"},
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("'score' must be an integer", str(context.exception))

    def test_empty_criteria_text(self):
        """Test that empty criteria text raises ValidationError."""
        invalid_options = [
            {"criteria": "   ", "score": 0},
        ]
        with self.assertRaises(ValidationError) as context:
            validate_review_criteria_options(invalid_options)
        self.assertIn("'criteria' cannot be empty", str(context.exception))

    def test_valid_with_extra_fields(self):
        """Test that extra fields are allowed."""
        valid_options = [
            {"criteria": "Poor", "score": 0, "extra_field": "value"},
            {"criteria": "Good", "score": 1},
        ]
        # Should not raise any exception
        validate_review_criteria_options(valid_options)
