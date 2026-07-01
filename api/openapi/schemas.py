from .content_schemas.registry import CONTENT_SCHEMAS
from .course_schemas import COURSE_SCHEMAS
from .integration_schemas import INTEGRATION_SCHEMAS


SCHEMAS = {}
SCHEMAS.update(COURSE_SCHEMAS)
SCHEMAS.update(CONTENT_SCHEMAS)
SCHEMAS.update(INTEGRATION_SCHEMAS)
