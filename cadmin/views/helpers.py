from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


CADMIN_PAGE_SIZE = 25


def paginate_queryset(request, queryset, per_page=CADMIN_PAGE_SIZE):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def pagination_querystring(request):
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


def redirect_after_action(request, default_view_name, **kwargs):
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default_view_name, **kwargs)


def first_form_error(form):
    form_error_values = form.errors.values()
    for errors in form_error_values:
        if errors:
            return errors[0]
    return "Invalid form data"


def staff_required(function):
    """Decorator to require staff/admin access"""
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and u.is_staff,
        login_url="/accounts/login/",
    )
    return actual_decorator(function)


def count_by(queryset, field):
    return list(
        queryset.values(field)
        .annotate(count=Count("id"))
        .order_by("-count", field)
    )
