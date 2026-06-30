from api.openapi_content_schemas import CONTENT_SCHEMAS
from api.openapi_course_schemas import COURSE_SCHEMAS
from api.openapi_integration_schemas import INTEGRATION_SCHEMAS


SCHEMAS = {}
SCHEMAS.update(COURSE_SCHEMAS)
SCHEMAS.update(CONTENT_SCHEMAS)
SCHEMAS.update(INTEGRATION_SCHEMAS)
