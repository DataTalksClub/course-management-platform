from django.urls import reverse

from ..client import public_url


def public_route_url(route_name, route_kwargs=None):
    if route_kwargs is None:
        path = reverse(route_name)
    else:
        path = reverse(route_name, kwargs=route_kwargs)
    url = public_url(path)
    return url
