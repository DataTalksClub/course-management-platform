from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from django.utils.html import urlize as urlize_impl

from accounts.services.timezones import format_user_datetime

register = template.Library()


@register.filter(is_safe=True, needs_autoescape=True)
@stringfilter
def urlize_target_blank(value, limit=30, autoescape=None):
    trim_url_limit = int(limit)
    urlized_value = urlize_impl(
        value,
        trim_url_limit=trim_url_limit,
        nofollow=True,
        autoescape=autoescape,
    )
    target_blank_value = urlized_value.replace("<a", '<a target="_blank"')
    return mark_safe(target_blank_value)


@register.filter
def user_datetime(value, user):
    return format_user_datetime(value, user)
