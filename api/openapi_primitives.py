from copy import deepcopy
from dataclasses import dataclass

from django.db import models

JSON = {"type": "object", "additionalProperties": True}


@dataclass(frozen=True)
class OperationData:
    url_name: str
    tags: list[str]
    summary: str
    responses: dict
    parameters: list | None = None
    body: dict | None = None
    requires_auth: bool | None = None
    description: str | None = None


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def array_of(schema):
    return {"type": "array", "items": schema}


def json_content(schema):
    return {"application/json": {"schema": schema}}


def response(description, schema=None):
    result = {"description": description}
    if schema is not None:
        result["content"] = json_content(schema)
    return result


def content_response(description, content):
    return {
        "description": description,
        "content": content,
    }


def request_body(schema):
    return {
        "required": True,
        "content": json_content(schema),
    }


def enum_schema(enum_class, *, nullable=False, description=None):
    values = []
    for item in enum_class:
        values.append(item.value)
    schema_type = "string"
    if nullable:
        values.append(None)
        schema_type = ["string", "null"]

    schema = {
        "type": schema_type,
        "enum": values,
    }
    if description:
        schema["description"] = description
    return schema


def choices_schema(choices, *, nullable=False):
    values = []
    for value, _label in choices:
        values.append(value)
    schema_type = "string"
    if nullable:
        values.append(None)
        schema_type = ["string", "null"]
    return {"type": schema_type, "enum": values}


MODEL_FIELD_SCHEMA_TYPES = (
    (models.BooleanField, {"type": "boolean"}),
    (models.IntegerField, {"type": "integer"}),
    (models.FloatField, {"type": "number"}),
    (models.DateTimeField, {"type": "string", "format": "date-time"}),
    (models.DateField, {"type": "string", "format": "date"}),
    (models.URLField, {"type": "string", "format": "uri"}),
)


def _typed_model_field_schema(field):
    for field_type, schema in MODEL_FIELD_SCHEMA_TYPES:
        if isinstance(field, field_type):
            return dict(schema)

    return {"type": "string"}


def model_field_schema(field):
    if field.choices:
        return choices_schema(field.choices, nullable=field.null)

    schema = _typed_model_field_schema(field)
    if field.null:
        schema["nullable"] = True

    return schema


def model_properties(model, fields):
    properties = {}
    for field_name in fields:
        field = model._meta.get_field(field_name)
        properties[field_name] = model_field_schema(field)
    return properties


def model_object_schema(
    model, fields, *, required_fields=None, extra_properties=None
):
    properties = model_properties(model, fields)
    if extra_properties:
        properties.update(extra_properties)

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required_fields:
        schema["required"] = required_fields
    return schema


def auth_required(operation):
    result = deepcopy(operation)
    result["security"] = [{"TokenAuth": []}]
    result.setdefault("responses", {})["401"] = response(
        "Authentication token missing or invalid",
        ref("Error"),
    )
    return result


def operation(data):
    result = {
        "tags": data.tags,
        "summary": data.summary,
        "operationId": data.url_name,
        "x-django-url-name": data.url_name,
        "responses": data.responses,
    }
    if data.description:
        result["description"] = data.description
    if data.parameters:
        result["parameters"] = data.parameters
    if data.body:
        result["requestBody"] = data.body
    if data.requires_auth is True:
        result = auth_required(result)
    return result
