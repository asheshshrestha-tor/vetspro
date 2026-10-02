"""Which branches a signed-in person can use, and which one they are working in.

The working branch is kept in the session. People with more than one branch can
also choose "All my branches", which shows lists for all of them together; pages
that create something at a branch then ask them to pick one first.
"""
from .models import Branch

SESSION_KEY = "dashboard_branch"
ALL = "all"


class BranchRequired(Exception):
    """Raised when a page needs one working branch but "All my branches" is selected."""


def _profile(user):
    return getattr(user, "staff_profile", None)


def allowed_branches(request):
    """Open branches this person may work in, cached on the request."""
    if not hasattr(request, "_allowed_branches"):
        user = request.user
        queryset = Branch.objects.filter(is_active=True)
        profile = _profile(user)
        if not (user.is_superuser or (profile and profile.all_branches)):
            queryset = queryset.filter(pk__in=profile.branches.values("pk")) if profile else queryset.none()
        request._allowed_branches = list(queryset.order_by("-is_main", "order", "name"))
    return request._allowed_branches


def current_branch(request):
    """The branch being worked in, or None when "All my branches" is selected."""
    if not hasattr(request, "_current_branch"):
        branches = allowed_branches(request)
        chosen = request.session.get(SESSION_KEY)
        branch = None
        if chosen == ALL and len(branches) > 1:
            branch = None
        else:
            branch = next((b for b in branches if str(b.pk) == str(chosen)), None)
            if branch is None and branches:
                profile = _profile(request.user)
                default_id = profile.default_branch_id if profile else None
                branch = next((b for b in branches if b.pk == default_id), branches[0])
        request._current_branch = branch
    return request._current_branch


def scope_ids(request):
    """Branch ids that lists show: the working branch, or all of the person's branches."""
    branch = current_branch(request)
    if branch is not None:
        return [branch.pk]
    return [b.pk for b in allowed_branches(request)]


def allowed_ids(request):
    return [b.pk for b in allowed_branches(request)]


def require_branch(request):
    """The working branch for creating something; raises BranchRequired in "All my branches" mode."""
    branch = current_branch(request)
    if branch is None:
        raise BranchRequired
    return branch


def is_all_mode(request):
    return current_branch(request) is None and len(allowed_branches(request)) > 1
