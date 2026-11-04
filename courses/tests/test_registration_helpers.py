from pathlib import Path
import re

from django.test import SimpleTestCase

from courses.registration import (
    COUNTRY_CHOICES,
    ordered_countries,
    region_for_country,
    render_markdown,
    youtube_embed_url,
)


class RegistrationHelperTests(SimpleTestCase):
    def test_youtube_watch_url_becomes_embed_url(self):
        url = "https://www.youtube.com/watch?v=abc123&feature=share"

        result = youtube_embed_url(url)

        self.assertEqual(result, "https://www.youtube.com/embed/abc123")

    def test_youtu_be_url_becomes_embed_url(self):
        url = "https://youtu.be/abc123?si=tracking"

        result = youtube_embed_url(url)

        self.assertEqual(result, "https://www.youtube.com/embed/abc123")

    def test_non_youtube_url_is_unchanged(self):
        url = "https://videos.example.com/watch?v=abc123"

        result = youtube_embed_url(url)

        self.assertEqual(result, url)

    def test_empty_youtube_url_stays_empty(self):
        result = youtube_embed_url("")

        self.assertEqual(result, "")

    def test_country_helpers_use_countries_config(self):
        countries = ordered_countries()
        germany_region = region_for_country("Germany")

        self.assertIn("Germany", countries)
        self.assertEqual(germany_region, "Europe")
        self.assertEqual(COUNTRY_CHOICES[0], ("United States", "United States"))


class MarkdownImageRenderingTests(SimpleTestCase):
    CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "courses.css"

    def test_markdown_image_renders_with_alt_and_title(self):
        html = render_markdown('![Diagram](https://example.com/d.png "Title")')

        self.assertIn(
            '<img src="https://example.com/d.png" alt="Diagram" title="Title">',
            html,
        )
        self.assertNotIn("&lt;img", html)

    def test_markdown_image_onerror_is_neutralized(self):
        html = render_markdown(
            '<img src="https://example.com/d.png" onerror="alert(1)" alt="Diagram">'
        )

        self.assertNotIn("onerror", html)
        self.assertIn('src="https://example.com/d.png"', html)

    def test_markdown_image_javascript_src_is_neutralized(self):
        html = render_markdown('<img src="javascript:alert(1)" alt="Diagram">')

        self.assertNotIn("javascript:", html)
        self.assertNotIn("src=", html)

    def test_markdown_disallowed_tags_still_escaped(self):
        html = render_markdown("<script>alert(1)</script>")

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_markdown_images_are_sized_responsively(self):
        css = self.CSS_PATH.read_text()

        rule = re.search(r"\.registration-markdown img\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertIn("max-width", rule.group(1))
        self.assertIn("height: auto", rule.group(1))
