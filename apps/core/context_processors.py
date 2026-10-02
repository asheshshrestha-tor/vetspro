from django.utils.functional import SimpleLazyObject

from .models import SiteSettings


def _open_branches():
    from apps.branches.models import Branch

    return list(Branch.objects.filter(is_active=True))


def site(request):
    branches = SimpleLazyObject(_open_branches)
    return {
        "site": SimpleLazyObject(SiteSettings.load),
        # The website lists branches only when there is more than one.
        "open_branches": branches,
        "branch_count": lambda: len(branches),  # templates call it when used
    }
