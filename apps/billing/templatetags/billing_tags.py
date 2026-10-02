from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def rs(value):
    """Nepali rupees with thousands separators: 1250.5 -> "Rs. 1,250.50"."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    return f"{sign}Rs. {abs(amount):,.2f}"


@register.filter
def qty(value):
    """Quantities without needless decimals: 2.00 -> "2", 0.50 -> "0.5"."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{amount.normalize():f}"


@register.filter
def stock_at(product, branch):
    """A product's stock at one branch."""
    if product is None:
        return ""
    return product.stock_at(branch)
