from django.http import HttpResponse


def disabled(request):
    return HttpResponse("This URL is disabled", status=403)
