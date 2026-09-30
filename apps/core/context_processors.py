from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def site(request):
    return {"site": SimpleLazyObject(SiteSettings.load)}
