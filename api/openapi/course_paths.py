from .primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


COURSE_PATHS_BY_URL_NAME = {
    "api_courses_list": {
        "get": operation(
            OperationData(
                "api_courses_list",
                ["Courses"],
                "List courses",
                {"200": response("Course list", ref("CoursesList"))},
            )
        ),
        "post": operation(
            OperationData(
                "api_courses_list",
                ["Courses"],
                "Create course",
                {
                    "201": response(
                        "Created course", ref("CourseDetail")
                    ),
                    "400": response("Invalid request", ref("Error")),
                },
                body=request_body(ref("CourseCreate")),
            )
        ),
    },
    "api_course_detail": {
        "get": operation(
            OperationData(
                "api_course_detail",
                ["Courses"],
                "Get course details",
                {
                    "200": response(
                        "Course details", ref("CourseDetail")
                    ),
                    "404": response("Course not found", ref("Error")),
                },
            )
        ),
        "patch": operation(
            OperationData(
                "api_course_detail",
                ["Courses"],
                "Update course",
                {
                    "200": response(
                        "Updated course", ref("CourseDetail")
                    ),
                    "400": response("Invalid field", ref("Error")),
                    "404": response("Course not found", ref("Error")),
                },
                body=request_body(ref("CoursePatch")),
            )
        ),
    },
    "api_registration_campaigns": {
        "get": operation(
            OperationData(
                "api_registration_campaigns",
                ["Registration Campaigns"],
                "List registration campaigns",
                {
                    "200": response(
                        "Registration campaign list",
                        ref("RegistrationCampaignsList"),
                    ),
                },
            )
        ),
        "post": operation(
            OperationData(
                "api_registration_campaigns",
                ["Registration Campaigns"],
                "Create registration campaign",
                {
                    "201": response(
                        "Created registration campaign",
                        ref("RegistrationCampaign"),
                    ),
                    "400": response("Invalid request", ref("Error")),
                },
                body=request_body(ref("RegistrationCampaignCreate")),
            )
        ),
    },
    "api_registration_campaign_detail": {
        "get": operation(
            OperationData(
                "api_registration_campaign_detail",
                ["Registration Campaigns"],
                "Get registration campaign",
                {
                    "200": response(
                        "Registration campaign",
                        ref("RegistrationCampaign"),
                    ),
                    "404": response(
                        "Registration campaign not found", ref("Error")
                    ),
                },
            )
        ),
        "patch": operation(
            OperationData(
                "api_registration_campaign_detail",
                ["Registration Campaigns"],
                "Update registration campaign",
                {
                    "200": response(
                        "Updated registration campaign",
                        ref("RegistrationCampaign"),
                    ),
                    "400": response("Invalid request", ref("Error")),
                    "404": response(
                        "Registration campaign not found", ref("Error")
                    ),
                },
                body=request_body(ref("RegistrationCampaignPatch")),
            )
        ),
    },
    "api_registration_campaign_registrations": {
        "get": operation(
            OperationData(
                "api_registration_campaign_registrations",
                ["Registration Campaigns"],
                "List registration campaign registrations and stats",
                {
                    "200": response(
                        "Registration campaign registrations",
                        ref("RegistrationCampaignRegistrations"),
                    ),
                    "404": response(
                        "Registration campaign not found", ref("Error")
                    ),
                },
            )
        ),
    },
}
