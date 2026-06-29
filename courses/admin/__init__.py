import logging

from pathlib import Path
from importlib import import_module

logger = logging.getLogger(__name__)


def import_admin_modules():
    # we just want to import all the modules,
    # so in admin.py we can use the star import
    current_dir = Path(__file__).resolve().parent

    python_files = current_dir.glob("*.py")
    for python_file in python_files:
        if python_file.name == "__init__.py":
            continue

        module_name = f"courses.admin.{python_file.stem}"

        try:
            import_module(module_name)
        except ImportError as e:
            logger.warning("Failed to import %s: %s", module_name, e)


import_admin_modules()
