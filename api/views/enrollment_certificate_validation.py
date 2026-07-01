def validate_certificate_update_items(certificate_updates):
    valid_updates = []
    errors = []

    for index, update in enumerate(certificate_updates):
        valid_update, error = validate_certificate_update_item(index, update)
        if error:
            errors.append(error)
            continue
        valid_updates.append(valid_update)

    return valid_updates, errors


def validate_certificate_update_item(index, update):
    if not isinstance(update, dict):
        error = invalid_certificate_update_item_error(index)
        return None, error

    email = update.get("email")
    certificate_path = update.get("certificate_path")

    if not email or not certificate_path:
        error = missing_certificate_update_fields_error(index, email)
        return None, error

    valid_update = {
        "index": index,
        "email": email,
        "certificate_path": certificate_path,
    }
    return valid_update, None


def invalid_certificate_update_item_error(index):
    return {
        "index": index,
        "code": "invalid_item",
        "error": "Each certificate update must be an object",
    }


def missing_certificate_update_fields_error(index, email):
    return {
        "index": index,
        "email": email,
        "code": "missing_fields",
        "error": "Both email and certificate_path are required",
    }
