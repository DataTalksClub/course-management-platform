from . import course, project, homework

from .course import *  # noqa: F403
from .homework import *  # noqa: F403
from .project import *  # noqa: F403

from django.contrib.auth import get_user_model

User = get_user_model()