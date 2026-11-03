"""Default reviewer messages for application decision emails.

These are starting texts shown in cadmin (editable before sending) and
the fixed location-policy text used by bulk-reject of excluded
applicants. The per-email mechanism (custom_message queued into the
Relay template context) lives in
``course_management.relay.application_notifications``.
"""

SLACK_JOIN_URL = "https://datatalks.club/slack.html"
SLACK_CHANNEL_URL = "https://app.slack.com/client/T01ATQK62F8/C0CEG1BUDKL"
SLACK_CHANNEL_NAME = "#course-ai-mediagen"
GITHUB_REPO_URL = "https://github.com/DataTalksClub/production-ai-agents-for-media-generation"
WORKSHOP_URL = "https://luma.com/tj2nbrl2"
YOUTUBE_URL = "https://www.youtube.com/watch?v=XzS6MrNfrcA"

APPROVAL_MESSAGE_LAUNCH = (
    "Before we start: join today's workshop at "
    f"{WORKSHOP_URL} - we'd love to see you there. "
    "Can't make it live? Watch the recording here: "
    f"{YOUTUBE_URL}\n"
    "\n"
    "Then star the course repo at "
    f"{GITHUB_REPO_URL} "
    "and join our Slack at "
    f"{SLACK_JOIN_URL} - come say hi in "
    f"[{SLACK_CHANNEL_NAME}]({SLACK_CHANNEL_URL}) "
    "to meet your cohort and get updates."
)

APPROVAL_MESSAGE_PERIODIC = (
    "Welcome aboard! Star the course repo at "
    f"{GITHUB_REPO_URL}, "
    "join our Slack at "
    f"{SLACK_JOIN_URL} "
    "and come say hi in "
    f"[{SLACK_CHANNEL_NAME}]({SLACK_CHANNEL_URL})."
)

REJECTION_MESSAGE_LOCATION = (
    "Due to your location, we unfortunately cannot give you access "
    "to the course environment for this cohort. Thank you for your "
    "interest - we hope to see you in a future opportunity.\n"
    "\n"
    "You are still welcome today: join our workshop at "
    f"{WORKSHOP_URL} - we'd love to see you there. "
    "Can't make it live? Watch the recording here: "
    f"{YOUTUBE_URL}"
)
