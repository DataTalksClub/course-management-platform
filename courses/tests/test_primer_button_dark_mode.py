from pathlib import Path
import re

from django.test import SimpleTestCase


CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "courses.css"


class PrimerButtonDarkModeTests(SimpleTestCase):
    def test_dark_mode_link_colors_do_not_override_primer_buttons(self):
        css = CSS_PATH.read_text()

        dark_link_rule = re.search(
            r"body\.dark-mode a:not\(\.primer-button\)\s*\{([^}]*)\}",
            css,
        )
        dark_link_hover_rule = re.search(
            r"body\.dark-mode a:not\(\.primer-button\):hover\s*\{([^}]*)\}",
            css,
        )

        self.assertIsNotNone(dark_link_rule)
        self.assertIsNotNone(dark_link_hover_rule)
        self.assertNotRegex(css, r"body\.dark-mode a\s*\{")
        self.assertRegex(
            css,
            r"\.primer-button\s*\{[^}]*color:\s*var\(--dk-text-on-accent\)",
        )

