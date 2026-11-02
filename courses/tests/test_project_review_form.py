from html.parser import HTMLParser

from django.test import Client
from django.urls import reverse

from courses.models import PeerReview, ProjectVote

from .project_list_view_base import ProjectListViewTestBase


class ReviewFormParser(HTMLParser):
    """Read the browser's form target and fields, not a hard-coded URL."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"attrs": attrs, "data": {}, "review": False}
        elif self.current is not None:
            if tag == "input" and "name" in attrs:
                self.current["data"][attrs["name"]] = attrs.get(
                    "value", ""
                )
            elif tag == "button":
                self.current["review"] = (
                    attrs.get("aria-label") == "Add to evaluation"
                )

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            if self.current["review"]:
                self.forms.append(self.current)
            self.current = None


class ProjectReviewFormTests(ProjectListViewTestBase):
    def test_submitted_student_can_add_review_via_rendered_form(self):
        self.peer_review.delete()
        self.assert_rendered_review_form_works()

    def test_volunteer_can_add_review_via_rendered_form(self):
        self.submission.delete()
        self.assert_rendered_review_form_works()

    def assert_rendered_review_form_works(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        response = self.client.get(self.project_list_url())
        self.assertEqual(response.status_code, 200)
        parser = ReviewFormParser()
        parser.feed(response.content.decode())
        self.assertEqual(len(parser.forms), 1)
        form = parser.forms[0]
        self.assertEqual(form["attrs"].get("method"), "post")
        self.assertTrue(form["data"].get("csrfmiddlewaretoken"))

        # Missing action means POST to the current page in a browser.
        target = form["attrs"].get("action") or self.project_list_url()
        response = self.client.post(target, form["data"])
        self.assertRedirects(response, self.project_list_url())
        review = PeerReview.objects.get(
            reviewer__student=self.user,
            submission_under_evaluation=self.other_submission,
        )
        self.assertTrue(review.optional)
        self.assertFalse(ProjectVote.objects.filter(voter=self.user).exists())
        self.assertContains(
            self.client.get(self.project_list_url()),
            reverse(
                "projects_eval_submit",
                args=[self.course.slug, self.project.slug, review.id],
            ),
        )

        # A repeated submission must not create a duplicate review.
        self.assertRedirects(
            self.client.post(target, form["data"]),
            self.project_list_url(),
        )
        self.assertEqual(
            PeerReview.objects.filter(
                reviewer__student=self.user,
                submission_under_evaluation=self.other_submission,
            ).count(),
            1,
        )
