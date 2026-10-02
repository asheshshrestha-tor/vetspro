from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from .registry import site


class StaffRequiredMixin(AccessMixin):
    """Signed-in staff only. Anyone else is sent to the dashboard's sign-in page."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_active and request.user.is_staff):
            return self.forbidden(request)
        from apps.branches.context import BranchRequired, allowed_branches

        if not allowed_branches(request):
            return render(request, "branches/no_branch.html", status=403)
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied:
            return self.forbidden(request)
        except BranchRequired:
            return render(request, "branches/choose_branch.html", {"branches": allowed_branches(request)})

    def forbidden(self, request):
        return render(request, "dashboard/403.html", status=403)


class ModuleMixin(StaffRequiredMixin):
    """Resolves the dashboard module named in the URL."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.module = site.get(kwargs.get("app_label"), kwargs.get("model_name"))

    def dispatch(self, request, *args, **kwargs):
        # Only staff learn whether a module exists; everyone else goes through the sign-in checks.
        if self.module is None and request.user.is_authenticated and request.user.is_staff:
            raise Http404("Unknown dashboard module.")
        return super().dispatch(request, *args, **kwargs)

    def require(self, allowed):
        if not allowed:
            raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(
            module=self.module,
            can_add=self.module.user_can_add(user),
            can_change=self.module.user_can_change(user),
            can_delete=self.module.user_can_delete(user),
            can_toggle=self.module.user_can_toggle(user),
        )
        return context
