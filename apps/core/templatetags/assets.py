import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def asset(path):
    """A static file URL that changes whenever the file changes, so browsers never use a stale copy.

    In production the manifest storage already puts a content hash in the name; in
    development the file's modification time is added instead.
    """
    url = static(path)
    if settings.DEBUG:
        found = finders.find(path)
        if found:
            url += f"?v={int(os.path.getmtime(found))}"
    return url
