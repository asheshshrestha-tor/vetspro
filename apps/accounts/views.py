from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView

from apps.dashboard.mixins import StaffRequiredMixin

from .forms import MyProfileForm
from .models import StaffProfile


class MyProfileView(StaffRequiredMixin, FormView):
    """Anyone signed in to the dashboard can update their own name and contact details."""

    template_name = "accounts/my_profile.html"
    form_class = MyProfileForm

    def get_profile(self):
        profile, _ = StaffProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_initial(self):
        user = self.request.user
        profile = self.get_profile()
        return {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": profile.phone,
            "designation": profile.designation,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile"] = self.get_profile()
        return context

    def form_valid(self, form):
        user = self.request.user
        data = form.cleaned_data
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.email = data["email"]
        user.save(update_fields=["first_name", "last_name", "email"])

        profile = self.get_profile()
        profile.phone = data["phone"]
        profile.designation = data["designation"]
        profile.save(update_fields=["phone", "designation"])

        messages.success(self.request, "Your profile has been updated.")
        return redirect("dashboard:my_profile")
