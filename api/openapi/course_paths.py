from .primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


COURSES_LIST_REF = ref("CoursesList")
COURSE_DETAIL_REF = ref("CourseDetail")
COURSE_CREATE_REF = ref("CourseCreate")
COURSE_PATCH_REF = ref("CoursePatch")
REGISTRATION_CAMPAIGNS_LIST_REF = ref("RegistrationCampaignsList")
REGISTRATION_CAMPAIGN_REF = ref("RegistrationCampaign")
REGISTRATION_CAMPAIGN_CREATE_REF = ref("RegistrationCampaignCreate")
REGISTRATION_CAMPAIGN_PATCH_REF = ref("RegistrationCampaignPatch")
REGISTRATION_CAMPAIGN_REGISTRATIONS_REF = ref(
    "RegistrationCampaignRegistrations"
)
COURSE_REGISTRATIONS_BULK_CREATE_REF = ref("CourseRegistrationsBulkCreate")
COURSE_REGISTRATIONS_BULK_CREATE_RESULT_REF = ref(
    "CourseRegistrationsBulkCreateResult"
)
COURSE_REGISTRATION_REF = ref("CourseRegistration")
COURSE_REGISTRATION_PATCH_REF = ref("CourseRegistrationPatch")
ERROR_REF = ref("Error")
COURSES_LIST_SUCCESS_RESPONSE = response("Course list", COURSES_LIST_REF)
COURSES_CREATE_SUCCESS_RESPONSE = response(
    "Created course",
    COURSE_DETAIL_REF,
)
INVALID_REQUEST_RESPONSE = response("Invalid request", ERROR_REF)
COURSE_DETAIL_SUCCESS_RESPONSE = response("Course details", COURSE_DETAIL_REF)
COURSE_NOT_FOUND_RESPONSE = response("Course not found", ERROR_REF)
COURSE_PATCH_SUCCESS_RESPONSE = response("Updated course", COURSE_DETAIL_REF)
INVALID_FIELD_RESPONSE = response("Invalid field", ERROR_REF)
REGISTRATION_CAMPAIGNS_LIST_SUCCESS_RESPONSE = response(
    "Registration campaign list",
    REGISTRATION_CAMPAIGNS_LIST_REF,
)
REGISTRATION_CAMPAIGN_CREATE_SUCCESS_RESPONSE = response(
    "Created registration campaign",
    REGISTRATION_CAMPAIGN_REF,
)
REGISTRATION_CAMPAIGN_DETAIL_SUCCESS_RESPONSE = response(
    "Registration campaign",
    REGISTRATION_CAMPAIGN_REF,
)
REGISTRATION_CAMPAIGN_NOT_FOUND_RESPONSE = response(
    "Registration campaign not found",
    ERROR_REF,
)
REGISTRATION_CAMPAIGN_PATCH_SUCCESS_RESPONSE = response(
    "Updated registration campaign",
    REGISTRATION_CAMPAIGN_REF,
)
REGISTRATION_CAMPAIGN_REGISTRATIONS_SUCCESS_RESPONSE = response(
    "Registration campaign registrations",
    REGISTRATION_CAMPAIGN_REGISTRATIONS_REF,
)
COURSE_REGISTRATIONS_BULK_CREATE_SUCCESS_RESPONSE = response(
    "Bulk registration creation results",
    COURSE_REGISTRATIONS_BULK_CREATE_RESULT_REF,
)
COURSE_REGISTRATION_DETAIL_SUCCESS_RESPONSE = response(
    "Registration",
    COURSE_REGISTRATION_REF,
)
COURSE_REGISTRATION_PATCH_SUCCESS_RESPONSE = response(
    "Updated registration",
    COURSE_REGISTRATION_REF,
)
COURSE_REGISTRATION_NOT_FOUND_RESPONSE = response(
    "Registration not found",
    ERROR_REF,
)

COURSES_LIST_RESPONSES = {
    "200": COURSES_LIST_SUCCESS_RESPONSE,
}
COURSES_LIST_DATA = OperationData(
    "api_courses_list",
    ["Courses"],
    "List courses",
    COURSES_LIST_RESPONSES,
)
COURSES_LIST_OPERATION = operation(COURSES_LIST_DATA)

COURSES_CREATE_RESPONSES = {
    "201": COURSES_CREATE_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
}
COURSES_CREATE_BODY = request_body(COURSE_CREATE_REF)
COURSES_CREATE_DATA = OperationData(
    "api_courses_list",
    ["Courses"],
    "Create course",
    COURSES_CREATE_RESPONSES,
    body=COURSES_CREATE_BODY,
)
COURSES_CREATE_OPERATION = operation(COURSES_CREATE_DATA)

COURSE_DETAIL_RESPONSES = {
    "200": COURSE_DETAIL_SUCCESS_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
}
COURSE_DETAIL_DATA = OperationData(
    "api_course_detail",
    ["Courses"],
    "Get course details",
    COURSE_DETAIL_RESPONSES,
)
COURSE_DETAIL_OPERATION = operation(COURSE_DETAIL_DATA)

COURSE_PATCH_RESPONSES = {
    "200": COURSE_PATCH_SUCCESS_RESPONSE,
    "400": INVALID_FIELD_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
}
COURSE_PATCH_BODY = request_body(COURSE_PATCH_REF)
COURSE_PATCH_DATA = OperationData(
    "api_course_detail",
    ["Courses"],
    "Update course",
    COURSE_PATCH_RESPONSES,
    body=COURSE_PATCH_BODY,
)
COURSE_PATCH_OPERATION = operation(COURSE_PATCH_DATA)

REGISTRATION_CAMPAIGNS_RESPONSES = {
    "200": REGISTRATION_CAMPAIGNS_LIST_SUCCESS_RESPONSE,
}
REGISTRATION_CAMPAIGNS_DATA = OperationData(
    "api_registration_campaigns",
    ["Registration Campaigns"],
    "List registration campaigns",
    REGISTRATION_CAMPAIGNS_RESPONSES,
)
REGISTRATION_CAMPAIGNS_OPERATION = operation(REGISTRATION_CAMPAIGNS_DATA)

REGISTRATION_CAMPAIGN_CREATE_RESPONSES = {
    "201": REGISTRATION_CAMPAIGN_CREATE_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
}
REGISTRATION_CAMPAIGN_CREATE_BODY = request_body(
    REGISTRATION_CAMPAIGN_CREATE_REF
)
REGISTRATION_CAMPAIGN_CREATE_DATA = OperationData(
    "api_registration_campaigns",
    ["Registration Campaigns"],
    "Create registration campaign",
    REGISTRATION_CAMPAIGN_CREATE_RESPONSES,
    body=REGISTRATION_CAMPAIGN_CREATE_BODY,
)
REGISTRATION_CAMPAIGN_CREATE_OPERATION = operation(
    REGISTRATION_CAMPAIGN_CREATE_DATA
)

REGISTRATION_CAMPAIGN_DETAIL_RESPONSES = {
    "200": REGISTRATION_CAMPAIGN_DETAIL_SUCCESS_RESPONSE,
    "404": REGISTRATION_CAMPAIGN_NOT_FOUND_RESPONSE,
}
REGISTRATION_CAMPAIGN_DETAIL_DATA = OperationData(
    "api_registration_campaign_detail",
    ["Registration Campaigns"],
    "Get registration campaign",
    REGISTRATION_CAMPAIGN_DETAIL_RESPONSES,
)
REGISTRATION_CAMPAIGN_DETAIL_OPERATION = operation(
    REGISTRATION_CAMPAIGN_DETAIL_DATA
)

REGISTRATION_CAMPAIGN_PATCH_RESPONSES = {
    "200": REGISTRATION_CAMPAIGN_PATCH_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
    "404": REGISTRATION_CAMPAIGN_NOT_FOUND_RESPONSE,
}
REGISTRATION_CAMPAIGN_PATCH_BODY = request_body(
    REGISTRATION_CAMPAIGN_PATCH_REF
)
REGISTRATION_CAMPAIGN_PATCH_DATA = OperationData(
    "api_registration_campaign_detail",
    ["Registration Campaigns"],
    "Update registration campaign",
    REGISTRATION_CAMPAIGN_PATCH_RESPONSES,
    body=REGISTRATION_CAMPAIGN_PATCH_BODY,
)
REGISTRATION_CAMPAIGN_PATCH_OPERATION = operation(
    REGISTRATION_CAMPAIGN_PATCH_DATA
)

REGISTRATION_CAMPAIGN_REGISTRATIONS_RESPONSES = {
    "200": REGISTRATION_CAMPAIGN_REGISTRATIONS_SUCCESS_RESPONSE,
    "404": REGISTRATION_CAMPAIGN_NOT_FOUND_RESPONSE,
}
REGISTRATION_CAMPAIGN_REGISTRATIONS_DATA = OperationData(
    "api_registration_campaign_registrations",
    ["Registration Campaigns"],
    "List registration campaign registrations and stats",
    REGISTRATION_CAMPAIGN_REGISTRATIONS_RESPONSES,
)
REGISTRATION_CAMPAIGN_REGISTRATIONS_OPERATION = operation(
    REGISTRATION_CAMPAIGN_REGISTRATIONS_DATA
)

COURSE_REGISTRATIONS_BULK_CREATE_RESPONSES = {
    "201": COURSE_REGISTRATIONS_BULK_CREATE_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
    "404": REGISTRATION_CAMPAIGN_NOT_FOUND_RESPONSE,
}
COURSE_REGISTRATIONS_BULK_CREATE_BODY = request_body(
    COURSE_REGISTRATIONS_BULK_CREATE_REF
)
COURSE_REGISTRATIONS_BULK_CREATE_DATA = OperationData(
    "api_registration_campaign_registrations",
    ["Registration Campaigns"],
    "Bulk create registrations for a campaign",
    COURSE_REGISTRATIONS_BULK_CREATE_RESPONSES,
    body=COURSE_REGISTRATIONS_BULK_CREATE_BODY,
    description=(
        "Creates registrations from a list of {email, name, company_name, "
        "country, role, comment, accepted_newsletter} objects. Existing "
        "campaign+email registrations are skipped, not overwritten. "
        "Requires a staff token."
    ),
)
COURSE_REGISTRATIONS_BULK_CREATE_OPERATION = operation(
    COURSE_REGISTRATIONS_BULK_CREATE_DATA
)

COURSE_REGISTRATION_DETAIL_RESPONSES = {
    "200": COURSE_REGISTRATION_DETAIL_SUCCESS_RESPONSE,
    "404": COURSE_REGISTRATION_NOT_FOUND_RESPONSE,
}
COURSE_REGISTRATION_DETAIL_DATA = OperationData(
    "api_registration_campaign_registration_detail",
    ["Registration Campaigns"],
    "Get a single registration",
    COURSE_REGISTRATION_DETAIL_RESPONSES,
)
COURSE_REGISTRATION_DETAIL_OPERATION = operation(
    COURSE_REGISTRATION_DETAIL_DATA
)

COURSE_REGISTRATION_PATCH_RESPONSES = {
    "200": COURSE_REGISTRATION_PATCH_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
    "404": COURSE_REGISTRATION_NOT_FOUND_RESPONSE,
}
COURSE_REGISTRATION_PATCH_BODY = request_body(COURSE_REGISTRATION_PATCH_REF)
COURSE_REGISTRATION_PATCH_DATA = OperationData(
    "api_registration_campaign_registration_detail",
    ["Registration Campaigns"],
    "Update a single registration",
    COURSE_REGISTRATION_PATCH_RESPONSES,
    body=COURSE_REGISTRATION_PATCH_BODY,
    description=(
        "Updates fields on a single registration (e.g. correcting a "
        "country value). Email cannot be changed. Requires a staff token."
    ),
)
COURSE_REGISTRATION_PATCH_OPERATION = operation(
    COURSE_REGISTRATION_PATCH_DATA
)

COURSE_PATHS_BY_URL_NAME = {
    "api_courses_list": {
        "get": COURSES_LIST_OPERATION,
        "post": COURSES_CREATE_OPERATION,
    },
    "api_course_detail": {
        "get": COURSE_DETAIL_OPERATION,
        "patch": COURSE_PATCH_OPERATION,
    },
    "api_registration_campaigns": {
        "get": REGISTRATION_CAMPAIGNS_OPERATION,
        "post": REGISTRATION_CAMPAIGN_CREATE_OPERATION,
    },
    "api_registration_campaign_detail": {
        "get": REGISTRATION_CAMPAIGN_DETAIL_OPERATION,
        "patch": REGISTRATION_CAMPAIGN_PATCH_OPERATION,
    },
    "api_registration_campaign_registrations": {
        "get": REGISTRATION_CAMPAIGN_REGISTRATIONS_OPERATION,
        "post": COURSE_REGISTRATIONS_BULK_CREATE_OPERATION,
    },
    "api_registration_campaign_registration_detail": {
        "get": COURSE_REGISTRATION_DETAIL_OPERATION,
        "patch": COURSE_REGISTRATION_PATCH_OPERATION,
    },
}
