"""Release identity and target guards shared by the GitHub deploy steps."""

import re

DEV_SERVICE_UUID = "qjnpmney8j8ehfuqcmzpjtzt"


def release_tag(timestamp, short_sha, dev_only=False):
    tag = f"{timestamp}-{short_sha}"
    # The production poller accepts only YYYYMMDD-HHMMSS-<sha>.
    return f"dev-{tag}" if dev_only else tag


def service_uuid(dev_only, production_uuid):
    return DEV_SERVICE_UUID if dev_only else production_uuid


def validate_service(uuid, service, dev_only):
    if dev_only and (
        uuid != DEV_SERVICE_UUID or service.get("name") != "cmp-dev"
    ):
        raise ValueError("DEV-only deployment refused: target is not cmp-dev")


def set_migration_roles(compose_raw):
    """Give migrations to the private web service and checks to its worker."""
    if not isinstance(compose_raw, str):
        raise ValueError("Coolify compose must be a string")

    updated = _set_service_environment(compose_raw, "web", "1")
    return _set_service_environment(updated, "worker", "0")


def _set_service_environment(compose_raw, service_name, migration_mode):
    services = re.search(r"(?m)^services:[ \t]*(?:#.*)?$", compose_raw)
    if not services:
        raise ValueError("Coolify compose has no services mapping")

    service_pattern = re.compile(
        rf"(?m)^  {re.escape(service_name)}:[ \t]*(?:#.*)?$"
    )
    service_match = service_pattern.search(compose_raw, services.end())
    if not service_match:
        raise ValueError(f"Coolify compose is missing the {service_name} service")

    service_line_end = compose_raw.find("\n", service_match.start())
    if service_line_end < 0:
        raise ValueError(f"{service_name} service has no body")
    next_service = re.compile(
        r"(?m)^  [A-Za-z0-9_-]+:[ \t]*(?:#.*)?$",
    ).search(compose_raw, service_line_end + 1)
    service_end = next_service.start() if next_service else len(compose_raw)
    service_block = compose_raw[service_match.start() : service_end]

    environment_header = re.search(
        r"(?m)^    environment:[ \t]*(?:#.*)?$", service_block
    )
    inline_or_unsupported_environment = re.search(
        r"(?m)^    environment:", service_block
    )
    if inline_or_unsupported_environment and not environment_header:
        raise ValueError(
            f"{service_name} environment must use a YAML mapping"
        )

    value_line = f'      CMP_RUN_MIGRATIONS: "{migration_mode}"'
    if not environment_header:
        insert_at = service_line_end + 1
        environment_lines = f"    environment:\n{value_line}\n"
        return compose_raw[:insert_at] + environment_lines + compose_raw[insert_at:]

    environment_start = environment_header.end()
    environment_line_end = service_block.find(
        "\n", environment_header.end()
    )
    if environment_line_end < 0:
        environment_line_end = len(service_block)
    environment_end_match = re.search(
        r"(?m)^ {4}\S", service_block[environment_line_end + 1 :]
    )
    environment_end = (
        environment_line_end + 1 + environment_end_match.start()
        if environment_end_match
        else len(service_block)
    )
    environment_block = service_block[environment_start:environment_end]
    if re.search(r"(?m)^ {6}-\s", environment_block):
        raise ValueError(
            f"{service_name} environment must use a YAML mapping"
        )

    existing_values = list(
        re.finditer(
            r"(?m)^      CMP_RUN_MIGRATIONS\s*:\s*.*$", environment_block
        )
    )
    if len(existing_values) > 1:
        raise ValueError(f"{service_name} has duplicate CMP_RUN_MIGRATIONS entries")

    if existing_values:
        match = existing_values[0]
        absolute_start = service_match.start() + environment_start + match.start()
        absolute_end = service_match.start() + environment_start + match.end()
        return compose_raw[:absolute_start] + value_line + compose_raw[absolute_end:]

    insert_at = service_match.start() + environment_line_end + 1
    return compose_raw[:insert_at] + value_line + "\n" + compose_raw[insert_at:]
