from django.http import HttpResponse
from django.views.decorators.http import require_GET

ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /*/leaderboard/\n"
    "Disallow: /*/leaderboard\n"
    "Crawl-delay: 10\n"
)


@require_GET
def robots_txt_view(request):
    """Serve robots.txt: keep crawlers off the expensive leaderboard pages."""
    return HttpResponse(ROBOTS_TXT, content_type="text/plain")
