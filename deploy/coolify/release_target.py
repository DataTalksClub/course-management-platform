"""Release identity and target guards shared by the GitHub deploy steps."""

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
