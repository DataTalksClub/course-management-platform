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
ERROR_REF = ref("Error")

COURSES_LIST_RESPONSES = {
    "200": response("Course list", COURSES_LIST_REF),
}
COURSES_LIST_DATA = OperationData(
    "api_courses_list",
    ["Courses"],
    "List courses",
    COURSES_LIST_RESPONSES,
)
COURSES_LIST_OPERATION = operation(COURSES_LIST_DATA)

COURSES_CREATE_RESPONSES = {
    "201": response("Created course", COURSE_DETAIL_REF),
    "400": response("Invalid request", ERROR_REF),
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
    "200": response("Course details", COURSE_DETAIL_REF),
    "404": response("Course not found", ERROR_REF),
}
COURSE_DETAIL_DATA = OperationData(
    "api_course_detail",
    ["Courses"],
    "Get course details",
    COURSE_DETAIL_RESPONSES,
)
COURSE_DETAIL_OPERATION = operation(COURSE_DETAIL_DATA)

COURSE_PATCH_RESPONSES = {
    "200": response("Updated course", COURSE_DETAIL_REF),
    "400": response("Invalid field", ERROR_REF),
    "404": response("Course not found", ERROR_REF),
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
    "200": response(
        "Registration campaign list",
        REGISTRATION_CAMPAIGNS_LIST_REF,
    ),
}
REGISTRATION_CAMPAIGNS_DATA = OperationData(
    "api_registration_campaigns",
    ["Registration Campaigns"],
    "List registration campaigns",
    REGISTRATION_CAMPAIGNS_RESPONSES,
)
REGISTRATION_CAMPAIGNS_OPERATION = operation(REGISTRATION_CAMPAIGNS_DATA)

REGISTRATION_CAMPAIGN_CREATE_RESPONSES = {
    "201": response(
        "Created registration campaign",
        REGISTRATION_CAMPAIGN_REF,
    ),
    "400": response("Invalid request", ERROR_REF),
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
    "200": response("Registration campaign", REGISTRATION_CAMPAIGN_REF),
    "404": response("Registration campaign not found", ERROR_REF),
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
    "200": response(
        "Updated registration campaign",
        REGISTRATION_CAMPAIGN_REF,
    ),
    "400": response("Invalid request", ERROR_REF),
    "404": response("Registration campaign not found", ERROR_REF),
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
    "200": response(
        "Registration campaign registrations",
        REGISTRATION_CAMPAIGN_REGISTRATIONS_REF,
    ),
    "404": response("Registration campaign not found", ERROR_REF),
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
    },
}
