from django.test import SimpleTestCase

from courses.registration import (
    COUNTRY_CHOICES,
    ordered_countries,
    region_for_country,
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

        self.assertIn("Germany", countries)
        self.assertEqual(region_for_country("Germany"), "Europe")
        self.assertEqual(COUNTRY_CHOICES[0], ("United States", "United States"))
