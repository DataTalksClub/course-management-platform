import os
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "course_management.settings"
)
django.setup()


# 1. Run calculation script manually
from courses.scoring import calculate_wrapped_statistics

stats = calculate_wrapped_statistics(year=2025, force=True)

# 2. Set visibility flag to display on main page
stats.is_visible = True
stats.save()
