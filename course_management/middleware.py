import logging

from django.http import HttpResponse


class RequestHeaderLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        self.logger.info(f"Headers: {request.headers}")
        return self.get_response(request)


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass ALLOWED_HOSTS check for health check endpoint
        if request.path.startswith('/ping') and request.method == 'GET':
            return HttpResponse("OK")
        return self.get_response(request)