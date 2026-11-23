from django.test import TestCase
from django.urls import reverse

from courses.models import Course

TRACKS = {
    "ai-dev-tools-2026": "https://datatalks.club/academy/agentic-engineering/",
    "llm-zoomcamp-2026": "https://datatalks.club/academy/ai-engineering/",
}


class AcademyLinksTest(TestCase):
    def test_home_links_the_academy(self):
        response = self.client.get(reverse("course_list"))

        self.assertContains(response, 'href="https://datatalks.club/academy/"')

    def test_zoomcamp_pages_link_their_academy_track(self):
        for slug, href in TRACKS.items():
            course = Course.objects.create(title=slug, slug=slug, visible=True)
            response = self.client.get(reverse("course", kwargs={"course_slug": course.slug}))
            self.assertContains(response, f'href="{href}"')

    def test_other_course_pages_have_no_academy_link(self):
        course = Course.objects.create(title="Other", slug="other-2026", visible=True)
        response = self.client.get(reverse("course", kwargs={"course_slug": course.slug}))
        self.assertNotContains(response, "datatalks.club/academy")
