from .campaigns import (
    campaign_method_cases,
    campaign_upsert_expectation as campaign_upsert_expectation,
    campaign_upsert_payload as campaign_upsert_payload,
)
from .contacts import contact_method_cases
from .recipient_lists import recipient_list_method_cases
from .transactional import transactional_method_cases
from .types import (
    DatamailerRequestExpectation as DatamailerRequestExpectation,
)


def datamailer_method_cases():
    cases = []
    for case in contact_method_cases():
        cases.append(case)
    for case in recipient_list_method_cases():
        cases.append(case)
    for case in transactional_method_cases():
        cases.append(case)
    for case in campaign_method_cases():
        cases.append(case)
    return cases
