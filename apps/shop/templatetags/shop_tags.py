from decimal import Decimal, InvalidOperation

from django import template
from django.utils.http import urlencode

register = template.Library()

# Picked by the first matching word in the category's name; the tone sets its colours.
CATEGORY_LOOKS = [
    (("medicine", "pharma"), "fa-pills", "blue"),
    (("food", "treat"), "fa-bowl-food", "orange"),
    (("toy",), "fa-baseball", "green"),
    (("cage", "bed", "carrier"), "fa-house-chimney", "purple"),
    (("collar", "leash", "accessor"), "fa-bone", "teal"),
    (("groom", "hygiene", "shampoo"), "fa-soap", "pink"),
]


def _look(category):
    name = str(category or "").lower()
    for words, icon, tone in CATEGORY_LOOKS:
        if any(word in name for word in words):
            return icon, tone
    return "fa-paw", "blue"


@register.filter
def category_icon(category):
    return _look(category)[0]


@register.filter
def category_tone(category):
    return _look(category)[1]


@register.filter
def price(value):
    """Shop prices: "Rs. 2,450", or "Rs. 2,450.50" when there are paisa."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    if amount == amount.to_integral():
        return f"Rs. {amount:,.0f}"
    return f"Rs. {amount:,.2f}"


@register.simple_tag
def whatsapp_order(site, product, quantity=None):
    """A WhatsApp link with the order already written, or "" when no WhatsApp number is set."""
    if not site.whatsapp_href:
        return ""
    amount = f"{quantity} × " if quantity else ""
    text = f"Hello, I would like to order: {amount}{product.name} ({product.unit}, {price(product.price)})."
    return f"{site.whatsapp_href}?{urlencode({'text': text})}"


@register.simple_tag(takes_context=True)
def query_with(context, **changes):
    """The current query string with some values changed; empty values are dropped."""
    params = context["request"].GET.copy()
    params.pop("page", None)
    for key, value in changes.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
