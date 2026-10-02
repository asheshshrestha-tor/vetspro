from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import StaffRequiredMixin
from apps.dashboard.views import safe_next

from .context import ALL, SESSION_KEY, allowed_branches
from .models import Branch


class SwitchBranchView(StaffRequiredMixin, View):
    """Change the branch being worked in, or choose "All my branches"."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        choice = request.POST.get("branch", "")
        branches = allowed_branches(request)
        if choice == ALL and len(branches) > 1:
            request.session[SESSION_KEY] = ALL
            messages.info(request, "Showing all your branches.")
        else:
            branch = next((b for b in branches if str(b.pk) == choice), None)
            if branch is None:
                messages.error(request, "You do not work at that branch.")
            else:
                request.session[SESSION_KEY] = branch.pk
                messages.info(request, f"You are now working in {branch.name}.")
        # Record pages belong to one branch, so go back to lists rather than a record of another branch.
        target = safe_next(request, "")
        return redirect(target or "dashboard:home")


class BranchListView(TemplateView):
    """The website's Branches page. It only exists when the hospital has more than one open branch."""

    template_name = "branches/branch_list.html"

    def get(self, request, *args, **kwargs):
        self.branches = list(Branch.objects.filter(is_active=True))
        if len(self.branches) < 2:
            raise Http404("There is only one branch.")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["branches"] = self.branches
        return context

