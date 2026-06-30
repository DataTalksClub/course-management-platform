from copy import deepcopy

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse

from accounts.auth import token_required
from .paths import PATHS_BY_URL_NAME
from .primitives import auth_required
from .schemas import SCHEMAS

def documented_urlpatterns():
    from api.urls import urlpatterns as api_urlpatterns

    return api_urlpatterns


def _sample_url_value(name, converter, index):
    if converter.regex == "[0-9]+":
        return 100000 + index
    return f"openapi-{name.replace('_', '-')}"


def _reverse_kwargs(pattern):
    kwargs = {}
    converters = pattern.pattern.converters.items()
    for index, converter_item in enumerate(converters, start=1):
        name, converter = converter_item
        kwargs[name] = _sample_url_value(name, converter, index)
    return kwargs


def openapi_path_for_url_name(url_name):
    pattern = None
    urlpatterns = documented_urlpatterns()
    for candidate_pattern in urlpatterns:
        if candidate_pattern.name == url_name:
            pattern = candidate_pattern
            break
    if pattern is None:
        raise LookupError(f"No documented URL pattern named {url_name}")

    kwargs = _reverse_kwargs(pattern)
    path = reverse(url_name, kwargs=kwargs)

    for name, value in kwargs.items():
        path = path.replace(str(value), f"{{{name}}}", 1)

    return path


def pattern_for_url_name(url_name):
    urlpatterns = documented_urlpatterns()
    for pattern in urlpatterns:
        if pattern.name == url_name:
            return pattern
    raise LookupError(f"No documented URL pattern named {url_name}")


def view_for_url_name(url_name):
    return pattern_for_url_name(url_name).callback


def parameter_schema_for_converter(converter):
    if converter.regex == "[0-9]+":
        return {"type": "integer"}
    return {"type": "string"}


def path_parameters_for_url_name(url_name):
    pattern = pattern_for_url_name(url_name)
    parameters = []
    for name, converter in pattern.pattern.converters.items():
        parameter = {
            "name": name,
            "in": "path",
            "required": True,
            "schema": parameter_schema_for_converter(converter),
        }
        parameters.append(parameter)
    return parameters


def operation_with_inspected_parameters(url_name, operation):
    generated_parameters = path_parameters_for_url_name(url_name)
    explicit_parameters = []
    operation_parameters = operation.get("parameters", [])
    for parameter in operation_parameters:
        if parameter.get("in") != "path":
            explicit_parameters.append(parameter)
    if not generated_parameters and not explicit_parameters:
        return operation

    return operation | {
        "parameters": [
            *generated_parameters,
            *explicit_parameters,
        ]
    }


def apply_inspected_operation_metadata(url_name, operation):
    result = deepcopy(operation)
    result = operation_with_inspected_parameters(url_name, result)

    view = view_for_url_name(url_name)
    if getattr(view, "requires_token_auth", False):
        result = auth_required(result)

    return result


def routed_paths():
    paths = set()
    urlpatterns = documented_urlpatterns()
    for pattern in urlpatterns:
        if pattern.name == "api_openapi_json":
            continue
        path = openapi_path_for_url_name(pattern.name)
        paths.add(path)
    return paths


def routed_url_names():
    url_names = set()
    urlpatterns = documented_urlpatterns()
    for pattern in urlpatterns:
        if pattern.name != "api_openapi_json":
            url_names.add(pattern.name)
    return url_names


def route_coverage(paths):
    documented = set(paths)
    routed = routed_paths()

    return {
        "routed_count": len(routed),
        "documented_count": len(documented),
        "undocumented": sorted(routed - documented),
        "documented_without_route": sorted(documented - routed),
    }


def build_openapi_paths():
    paths = {}
    for url_name, methods in PATHS_BY_URL_NAME.items():
        openapi_path = openapi_path_for_url_name(url_name)
        method_operations = {}
        for method, operation in methods.items():
            inspected_operation = apply_inspected_operation_metadata(
                url_name,
                operation,
            )
            method_operations[method] = inspected_operation
        paths[openapi_path] = method_operations
    return paths

def build_openapi_spec():
    paths = build_openapi_paths()

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Course Management Platform API",
            "version": settings.VERSION,
            "description": (
                "Generated OpenAPI specification for the course management, "
                "course data export, and operational endpoints. Treat this "
                "document as the source of truth for agent API usage."
            ),
        },
        "paths": paths,
        "x-route-coverage": route_coverage(paths),
        "components": {
            "securitySchemes": {
                "TokenAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Use `Token <token_key>`.",
                },
            },
            "schemas": deepcopy(SCHEMAS),
        },
    }


@token_required
def openapi_json_view(request):
    spec = build_openapi_spec()
    response = JsonResponse(spec)
    return response
