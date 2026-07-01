from .types import DatamailerMethodCase


def upsert_contact_method_case():
    payload = {"email": "student@example.com"}
    return DatamailerMethodCase(
        method_name="upsert_contact",
        args=(payload,),
        method="POST",
        path="/api/contacts",
        json_payload=payload,
        response_payload={"ok": True},
        expected_result={"ok": True},
    )


def bulk_import_contacts_method_case():
    contact = {"email": "student@example.com"}
    contacts = []
    contacts.append(contact)
    contact_import_payload = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "contacts": contacts,
    }
    return DatamailerMethodCase(
        method_name="bulk_import_contacts",
        args=(contact_import_payload,),
        method="POST",
        path="/api/contacts/imports",
        json_payload=contact_import_payload,
        response_payload={"counts": {"created": 1}},
        expected_result={"counts": {"created": 1}},
    )


def erase_contact_method_case():
    erase_payload = {
        "email": "student@example.com",
        "audience": "dtc-courses",
        "client": "dtc-courses",
    }
    return DatamailerMethodCase(
        method_name="erase_contact",
        args=("student@example.com",),
        method="POST",
        path="/api/contacts/erase",
        json_payload=erase_payload,
        response_payload={"erased": True},
        expected_result={"erased": True},
    )


def contact_write_method_cases():
    cases = []

    upsert_case = upsert_contact_method_case()
    cases.append(upsert_case)

    import_case = bulk_import_contacts_method_case()
    cases.append(import_case)

    erase_case = erase_contact_method_case()
    cases.append(erase_case)

    return cases


def contact_status_method_case():
    params = {
        "email": "student@example.com",
        "audience": "dtc-courses",
        "client": "dtc-courses",
    }
    return DatamailerMethodCase(
        method_name="contact_status",
        args=("student@example.com",),
        method="GET",
        path="/api/contacts/status",
        params=params,
        response_payload={"exists": True},
        expected_result={"exists": True},
    )


def contact_history_method_case():
    params = {
        "audience": "dtc-courses",
        "client": "dtc-courses",
        "limit": 5,
    }
    kwargs = {"limit": 5}
    return DatamailerMethodCase(
        method_name="contact_history",
        args=(42,),
        kwargs=kwargs,
        method="GET",
        path="/api/contacts/42/history",
        params=params,
        response_payload={"transactional_messages": []},
        expected_result={"transactional_messages": []},
    )


def contact_read_method_cases():
    cases = []
    case = contact_status_method_case()
    cases.append(case)
    case = contact_history_method_case()
    cases.append(case)
    return cases


def contact_method_cases():
    cases = []
    for case in contact_write_method_cases():
        cases.append(case)
    for case in contact_read_method_cases():
        cases.append(case)
    return cases
