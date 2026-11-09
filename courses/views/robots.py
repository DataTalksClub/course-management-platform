from django.http import HttpResponse
from django.views.decorators.http import require_GET

ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /*/leaderboard/\n"
    "Disallow: /*/leaderboard\n"
    "Allow: /*/leaderboard$\n"
    "Disallow: /accounts/\n"
    "Disallow: /api/\n"
    "Disallow: /admin/\n"
    "Disallow: /cadmin/\n"
    "Crawl-delay: 10\n"
)


@require_GET
def robots_txt_view(request):
    """Allow canonical leaderboard pages, excluding queries and subpages.

    The end anchor is intentional: even ?page=1 is a duplicate URL.
    Googlebot uses the longest matching rule, with Allow winning ties.
    """
    return HttpResponse(ROBOTS_TXT, content_type="text/plain")
