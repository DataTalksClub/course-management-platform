from pathlib import Path
from unittest import SkipTest

from django.test import SimpleTestCase

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "courses.css"

PAGE = """
<html>
<head><style>{css}</style></head>
<body style="width: 1200px">
  <div class="question" style="padding-left: 200px">
    <label for="github_link" class="question-text font-medium">
      {label}
      <span class="form-help-icon app-muted"
            role="button"
            tabindex="0"
            data-form-help="Your project should be hosted on GitHub. Make sure your project is public">?</span>
    </label>
    <input type="url" id="github_link" />
  </div>
</body>
</html>
"""


class FormHelpTooltipTestCase(SimpleTestCase):
    """Rendered layout of the ? help tooltip next to form labels."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if sync_playwright is None:
            raise SkipTest("playwright is not installed")
        cls._playwright = sync_playwright().start()
        try:
            cls._browser = cls._playwright.chromium.launch()
        except PlaywrightError as exc:
            cls._playwright.stop()
            raise SkipTest(f"chromium is not available: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()
        super().tearDownClass()

    def tooltip_width(self, label):
        page = self._browser.new_page(viewport={"width": 1200, "height": 800})
        css = CSS_PATH.read_text()
        page.set_content(PAGE.format(css=css, label=label))
        page.focus(".form-help-icon")

        tooltip_width = page.evaluate(
            """() => {
                const icon = document.querySelector('.form-help-icon');
                return parseFloat(getComputedStyle(icon, '::after').width);
            }"""
        )
        page.close()
        return tooltip_width

    def test_tooltip_is_wide_enough_to_read(self):
        # The tooltip was squeezed to the ~14px icon width, one word per line.
        for label in ["GitHub link to the project", "Commit ID"]:
            with self.subTest(label=label):
                self.assertGreaterEqual(self.tooltip_width(label), 200)
