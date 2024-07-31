import logging

from unittest import TestCase

from courses.validators.custom_url_validators import (
    validate_url_200,
    get_error_message,
)
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class UrlValidationTestCase(TestCase):

    def test_validation_code_200_github_mock(self):
        mock_get = lambda url: MockResponse(200)
        url = "https://github.com/DataTalksClub/"
        validate_url_200(url, mock_get)
        # no exceptions should be raised

    def test_validation_code_404_github_mock(self):
        mock_get = lambda url: MockResponse(404)
        url = "https://github.com/DataTalksClub/non-existing-repo"
        with self.assertRaises(ValidationError):
            validate_url_200(url, mock_get)

    def test_error_message_404_github(self):
        url = "https://github.com/DataTalksClub/non-existing-repo"
        error = get_error_message(404, url)
        expected_error = (
            f"The submitted GitHub link {url} does not "
            + "exist. Make sure the repository is public."
        )
        self.assertEqual(error, expected_error)

    def test_error_message_404_github_case_insensitive(self):
        url = "https://GitHub.com/DataTalksClub/non-existing-repo"
        error = get_error_message(404, url)
        expected_error = (
            f"The submitted GitHub link {url} does not "
            + "exist. Make sure the repository is public."
        )
        self.assertEqual(error, expected_error)

    def test_error_message_404_linkedin(self):
        url = "https://www.linkedin.com/feed/update/urn:li:activity:7221077695688773633/"
        error = get_error_message(404, url)
        expected_error = f"The submitted link {url} does not exist."
        self.assertEqual(error, expected_error)

    def test_error_message_400(self):
        url = "https://www.linkedin.com/whatever"
        error = get_error_message(400, url)
        expected_error = (
            f"The submitted link {url} does not "
            + "return a 200 status code. Status code: 400."
        )
        self.assertEqual(error, expected_error)
