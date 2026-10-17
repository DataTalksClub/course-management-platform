"""Read or change timing through the authenticated CMP API."""

import json
import os
from urllib.parse import quote, urlsplit

import requests
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Read or update course/homework/project timing using a staff API token."

    def add_arguments(self, parser):
        parser.add_argument("course_slug")
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--token-env", default="AUTH_TOKEN")
        target = parser.add_mutually_exclusive_group()
        target.add_argument("--homework")
        target.add_argument("--project")
        start = parser.add_mutually_exclusive_group()
        start.add_argument("--starts-at")
        start.add_argument("--clear-start", action="store_true")
        for field in (
            "start_date",
            "end_date",
            "due_date",
            "submission_due_date",
            "peer_review_due_date",
        ):
            parser.add_argument("--" + field.replace("_", "-"))

    def handle(self, *args, **options):
        url = timing_url(options)
        token = os.environ.get(options["token_env"])
        if not token:
            raise CommandError(
                "API token environment variable is missing."
            )
        payload = timing_payload(options)
        method = "GET"
        if payload:
            method = "PATCH"
        try:
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Token {token}"},
                json=payload or None,
                timeout=30,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise CommandError("CMP API request failed.") from None
        if response.status_code >= 300:
            raise CommandError(
                f"CMP API rejected the request (HTTP {response.status_code})."
            )
        self.stdout.write(json.dumps(response.json(), indent=2))


def timing_url(options):
    base = options["base_url"].rstrip("/")
    parsed = urlsplit(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and local
    ):
        raise CommandError(
            "Use HTTPS, or HTTP on localhost for local testing."
        )
    if (
        not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise CommandError(
            "Use a base origin without credentials, path, query or fragment."
        )
    url = (
        f"{base}/api/courses/{quote(options['course_slug'], safe='')}/"
    )
    for kind in ("homework", "project"):
        slug = options[kind]
        if slug:
            url += f"{kind}s/by-slug/{quote(slug, safe='')}/"
    return url


def timing_payload(options):
    allowed = ("start_date", "end_date")
    if options["homework"]:
        allowed = ("due_date",)
    if options["project"]:
        allowed = ("submission_due_date", "peer_review_due_date")
    payload = {}
    for field in (
        "start_date",
        "end_date",
        "due_date",
        "submission_due_date",
        "peer_review_due_date",
    ):
        if options[field] is None:
            continue
        if field not in allowed:
            raise CommandError(
                f"{field} does not apply to this target."
            )
        payload[field] = options[field]
    if options["starts_at"] is not None:
        payload["starts_at"] = options["starts_at"]
    if options["clear_start"]:
        payload["starts_at"] = None
    return payload
