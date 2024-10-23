from pathlib import Path
from importlib import import_module


def import_admin_modules():
    # we just want to import all the modules,
    # so in admin.py we can use the star import
    current_dir = Path(__file__).resolve().parent

    for python_file in current_dir.glob("*.py"):
        if python_file.name == "__init__.py":
            continue

        module_name = f"courses.admin.{python_file.stem}"

        try:
            import_module(module_name)
        except ImportError as e:
            print(f"Failed to import {module_name}: {e}")


import_admin_modules()
