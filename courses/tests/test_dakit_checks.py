import shutil
import subprocess
from pathlib import Path
from unittest import SkipTest

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]
DAKIT_DIR = REPO_ROOT / "courses" / "static" / "dakit"


class DakitChecksTestCase(SimpleTestCase):
    """Ensure vendored dakit assets stay in sync and CSS/templates pass dakit checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.node_bin = shutil.which("node")
        if cls.node_bin is None:
            raise SkipTest("node is not installed")

    def _run_node_check(self, script_name: str, *args: str) -> None:
        result = subprocess.run(
            [self.node_bin, str(DAKIT_DIR / script_name), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"{script_name} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )

    def test_dakit_vendor_lock_in_sync(self):
        self._run_node_check("sync.mjs", "--check", "--dest", "courses/static/dakit")

    def test_dakit_borders_check(self):
        self._run_node_check("check-borders.mjs", ".")

    def test_dakit_colors_check(self):
        self._run_node_check("check-colors.mjs", ".")

    def test_dakit_scale_check(self):
        self._run_node_check("check-scale.mjs", ".")
