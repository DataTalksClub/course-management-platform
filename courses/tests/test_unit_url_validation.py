import socket
from unittest.mock import patch
from unittest import TestCase
import requests

from courses.validators.custom_url_validators import (
    URL_VALIDATION_TIMEOUT,
    clean_faq_contribution_url,
    is_github_repository_url,
    validate_github_repository_url,
    validate_url_200,
    get_error_message,
)
from django.core.exceptions import ValidationError


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FaqContributionUrlValidationTestCase(TestCase):
    def test_clean_faq_contribution_url_strips_valid_issue_url(self):
        url = " https://github.com/DataTalksClub/faq/issues/281 "

        cleaned = clean_faq_contribution_url(url)

        self.assertEqual(
            cleaned, "https://github.com/DataTalksClub/faq/issues/281"
        )

    def test_clean_faq_contribution_url_accepts_pull_url(self):
        url = "https://github.com/DataTalksClub/faq/pull/266"

        cleaned = clean_faq_contribution_url(url)

        self.assertEqual(cleaned, url)

    def test_clean_faq_contribution_url_rejects_non_https_url(self):
        url = "http://github.com/DataTalksClub/faq/issues/281"

        with self.assertRaises(ValidationError) as context:
            clean_faq_contribution_url(url)

        self.assertEqual(
            context.exception.message_dict["faq_contribution_url"],
            [
                "FAQ contribution must be a valid HTTPS GitHub issue "
                "or pull request URL."
            ],
        )

    def test_clean_faq_contribution_url_rejects_other_github_urls(self):
        url = "https://gist.github.com/Sanjomwa/hash"

        with self.assertRaises(ValidationError) as context:
            clean_faq_contribution_url(url)

        self.assertEqual(
            context.exception.message_dict["faq_contribution_url"],
            [
                "FAQ contribution must be a DataTalksClub/faq issue "
                "or pull request URL, for example "
                "https://github.com/DataTalksClub/faq/issues/281."
            ],
        )

    def test_clean_faq_contribution_url_rejects_other_datatalksclub_repos(
        self,
    ):
        """A contribution to another DataTalksClub repository is not an FAQ
        contribution, even though the org and the URL shape both match."""
        other_repo_urls = [
            "https://github.com/DataTalksClub/machine-learning-zoomcamp/pull/292",
            "https://github.com/DataTalksClub/data-engineering-zoomcamp/issues/12",
            "https://github.com/DataTalksClub/mlops-zoomcamp/pull/1",
        ]

        for url in other_repo_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError) as context:
                    clean_faq_contribution_url(url)

                self.assertEqual(
                    context.exception.message_dict["faq_contribution_url"],
                    [
                        "FAQ contribution must be a DataTalksClub/faq issue "
                        "or pull request URL, for example "
                        "https://github.com/DataTalksClub/faq/issues/281."
                    ],
                )

    def test_clean_faq_contribution_url_rejects_faq_repo_in_another_org(self):
        url = "https://github.com/someone-else/faq/pull/1"

        with self.assertRaises(ValidationError):
            clean_faq_contribution_url(url)


class UrlStatusValidationTestCase(TestCase):
    def setUp(self):
        resolver = patch(
            "socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                )
            ],
        )
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_validation_code_200_github_mock(self):
        def mock_get(url, **kwargs):
            return MockResponse(200)

        url = "https://github.com/DataTalksClub/"
        validate_url_200(url, mock_get)
        # no exceptions should be raised

    def test_validation_code_404_github_mock(self):
        def mock_get(url, **kwargs):
            return MockResponse(404)

        url = "https://github.com/DataTalksClub/non-existing-repo"
        with self.assertRaises(ValidationError):
            validate_url_200(url, mock_get)

    def test_timeout_is_passed_to_request(self):
        captured = {}

        def mock_get(url, **kwargs):
            captured.update(kwargs)
            return MockResponse(200)

        validate_url_200("https://example.com/", mock_get)
        self.assertIn("timeout", captured)
        self.assertIsInstance(captured["timeout"], tuple)
        self.assertLessEqual(sum(captured["timeout"]), URL_VALIDATION_TIMEOUT)

    def test_non_requests_exception_becomes_validation_error(self):
        # e.g. UnicodeError / LocationParseError from a malformed host -
        # must not escape as an uncaught 500.
        def mock_get(url, **kwargs):
            raise UnicodeError("label too long")

        with self.assertRaises(ValidationError):
            validate_url_200("https://example.com/", mock_get)

    def test_rejects_loopback_before_requesting_url(self):
        response_method = patch(
            "socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 8000),
                )
            ],
        )
        with response_method:
            get_method = patch(
                "courses.validators.custom_url_validators.requests.head",
                return_value=MockResponse(200),
            )
            with get_method as request:
                with self.assertRaises(ValidationError):
                    validate_url_200("http://localhost:8000/", request)

        request.assert_not_called()

    def test_rejects_private_link_local_and_nonstandard_ports(self):
        unsafe_targets = [
            ("http://169.254.169.254/", "169.254.169.254"),
            ("http://10.100.0.2:5432/", "10.100.0.2"),
            ("http://example.com:8080/", "93.184.216.34"),
        ]
        for url, address in unsafe_targets:
            with self.subTest(url=url):
                resolver = patch(
                    "socket.getaddrinfo",
                    return_value=[
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            socket.IPPROTO_TCP,
                            "",
                            (address, 443),
                        )
                    ],
                )
                with resolver:
                    with patch(
                        "courses.validators.custom_url_validators.requests.head",
                        return_value=MockResponse(200),
                    ) as request:
                        with self.assertRaises(ValidationError):
                            validate_url_200(url, request)
                        request.assert_not_called()

    def test_http_requests_do_not_follow_redirects(self):
        captured = {}

        def mock_get(url, **kwargs):
            captured.update(kwargs)
            return MockResponse(200)

        validate_url_200("https://example.com/", mock_get)

        self.assertFalse(captured["allow_redirects"])

    def test_get_fallback_is_streamed_and_does_not_follow_redirects(self):
        captured = {}

        def mock_head(url, **kwargs):
            return MockResponse(405)

        def mock_get(url, **kwargs):
            captured.update(kwargs)
            return MockResponse(200)

        with patch(
            "courses.validators.custom_url_validators.requests.get",
            side_effect=mock_get,
        ):
            validate_url_200("https://example.com/", mock_head)

        self.assertFalse(captured["allow_redirects"])
        self.assertTrue(captured["stream"])
        self.assertLessEqual(sum(captured["timeout"]), URL_VALIDATION_TIMEOUT)

    def test_network_error_is_not_reflected_to_the_user(self):
        def mock_get(url, **kwargs):
            raise requests.ConnectionError(
                "private host 10.100.0.2 refused the connection"
            )

        with self.assertRaises(ValidationError) as context:
            validate_url_200("https://example.com/", mock_get)

        self.assertNotIn("10.100.0.2", str(context.exception))


class UrlErrorMessageTestCase(TestCase):
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


class GithubRepositoryUrlValidationTestCase(TestCase):
    def test_accepts_github_repository_urls(self):
        for url in [
            "https://github.com/owner/repo",
            "https://www.github.com/owner/repo/tree/main",
            "http://github.com/owner/repo/",
        ]:
            self.assertTrue(is_github_repository_url(url), url)

    def test_rejects_non_github_urls(self):
        for url in [
            "https://httpbin.org/status/200",
            "https://gitlab.com/owner/repo",
            "https://github.com.evil.com/owner/repo",
            "https://evil.com/github.com/owner/repo",
            "https://github.com/owner",
            "https://github.com/",
            "ftp://github.com/owner/repo",
            "",
        ]:
            self.assertFalse(is_github_repository_url(url), url)
            with self.assertRaises(ValidationError):
                validate_github_repository_url(url)
