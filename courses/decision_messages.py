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

APPROVAL_MESSAGE_LAUNCH = (
    "Before we start: join today's workshop at "
    f"{WORKSHOP_URL} — we'd love to see you there. "
    "Then star the course repo at "
    f"{GITHUB_REPO_URL} "
    "and join our Slack at "
    f"{SLACK_JOIN_URL} — come say hi in "
    f"{SLACK_CHANNEL_NAME} ({SLACK_CHANNEL_URL}) "
    "to meet your cohort and get updates. "
    "Know someone who would love this course? Invite them with your "
    "personal invite link below — you'll earn 3 leaderboard points "
    "for each invitee who gets accepted. "
    "And share the news that you got in: post "
    "'I was accepted to Production AI Agents for Generative Media — "
    "see you in class!' on LinkedIn or X so others can join too."
)

APPROVAL_MESSAGE_PERIODIC = (
    "Welcome aboard! Star the course repo at "
    f"{GITHUB_REPO_URL}, "
    "join our Slack at "
    f"{SLACK_JOIN_URL} "
    "and come say hi in "
    f"{SLACK_CHANNEL_NAME} ({SLACK_CHANNEL_URL}). "
    "Know someone who would love this course? Invite them with your "
    "personal invite link below — you'll earn 3 leaderboard points "
    "for each invitee who gets accepted. "
    "And share the news that you got in: post "
    "'I was accepted to Production AI Agents for Generative Media — "
    "see you in class!' on LinkedIn or X so others can join too."
)

REJECTION_MESSAGE_LOCATION = (
    "Due to your location, we unfortunately cannot give you access "
    "to the course environment for this cohort. Thank you for your "
    "interest — we hope to see you in a future opportunity."
)
