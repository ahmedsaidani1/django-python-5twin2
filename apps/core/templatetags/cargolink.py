from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_current(context, *prefixes):
    """Return ``aria-current="page"`` when the current path starts with one of the URL prefixes."""
    path = context["request"].path
    for prefix in prefixes:
        if (prefix == "/" and path == "/") or (prefix != "/" and path.startswith(prefix)):
            return format_html('aria-current="page"')
    return ""


@register.inclusion_tag("partials/status_badge.html")
def status_badge(obj):
    return {"value": obj.status, "label": obj.get_status_display()}


@register.inclusion_tag("partials/stars.html")
def stars(rating):
    value = round(float(rating or 0))
    return {"full": range(value), "empty": range(5 - value), "rating": rating}


@register.filter
def tnd(value):
    if value in (None, ""):
        return "—"
    return f"{float(value):,.2f} TND".replace(",", " ").replace(".", ",")
