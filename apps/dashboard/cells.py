"""Turns model values into the cells shown in dashboard lists and detail pages."""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import formats, timezone
from django.utils.text import Truncator

from .registry import Badge


def resolve_field(model, path):
    """The model field at the end of a lookup such as "pet__species"."""
    field = None
    for part in path.split("__"):
        field = model._meta.get_field(part)
        if field.is_relation:
            model = field.related_model
    return field


def object_label(obj):
    """How a related record is named in cells and filters. Staff show by their full name."""
    if isinstance(obj, get_user_model()):
        return obj.get_full_name() or obj.get_username()
    return str(obj)


def column_label(module, name):
    try:
        label = resolve_field(module.model, name).verbose_name
    except FieldDoesNotExist:
        attr = getattr(module, name, None) or getattr(module.model, name, None)
        label = getattr(attr, "short_description", name.replace("_", " "))
    return str(label)[:1].upper() + str(label)[1:]


def get_value(module, obj, name):
    """A column is a model field, a method on the module, or an attribute of the object."""
    method = getattr(module, name, None)
    if callable(method) and not hasattr(obj, name):
        return method(obj)
    display = getattr(obj, f"get_{name}_display", None)
    if callable(display):
        return display()
    value = getattr(obj, name)
    return value() if callable(value) else value


def build_cell(module, obj, name, truncate=70):
    value = get_value(module, obj, name)
    cell = {"name": name, "kind": "text", "value": value, "toggle": name in module.toggle_fields}

    try:
        field = module.opts.get_field(name)
    except FieldDoesNotExist:
        field = None

    if isinstance(value, Badge):
        cell.update(kind="badge", value=value.label, color=value.color)
    elif isinstance(field, models.ImageField):
        cell.update(kind="image", value=value.url if value else "")
    elif isinstance(value, bool):
        cell["kind"] = "bool"
    elif value in (None, ""):
        cell.update(kind="empty", value="")
    elif isinstance(value, datetime.datetime):
        cell["value"] = formats.date_format(timezone.localtime(value), "j M Y, H:i")
    elif isinstance(value, datetime.date):
        cell["value"] = formats.date_format(value, "j M Y")
    elif isinstance(value, datetime.time):
        cell["value"] = formats.time_format(value, "H:i")
    elif isinstance(value, Decimal):
        cell["value"] = formats.number_format(value, use_l10n=True, force_grouping=True)
    elif isinstance(field, models.URLField):
        cell["kind"] = "link"
    elif isinstance(field, models.EmailField):
        cell["kind"] = "email"
    else:
        text = object_label(value) if isinstance(value, models.Model) else str(value)
        cell["value"] = Truncator(text).chars(truncate) if truncate else text
        if truncate is None and "\n" in text:
            cell["kind"] = "multiline"
    return cell
