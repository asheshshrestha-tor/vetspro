from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.dashboard.forms import DashboardForm, DashboardModelForm
from apps.dashboard.registry import site

from .models import StaffProfile

User = get_user_model()

PROFILE_FIELDS = ["designation", "phone", "licence_number", "can_attend"]


class StaffUserForm(DashboardModelForm):
    role = forms.ModelChoiceField(queryset=Group.objects.order_by("name"), help_text="Decides what this person can see and do.")
    designation = forms.CharField(max_length=100, required=False, help_text="e.g. Senior Veterinarian")
    phone = forms.CharField(max_length=30, required=False)
    licence_number = forms.CharField(label="Registration / licence number", max_length=60, required=False)
    can_attend = forms.BooleanField(
        label="Can attend appointments",
        required=False,
        initial=True,
        help_text="Shown in the “Attended by” list on appointments. Untick for non-clinical staff.",
    )
    password1 = forms.CharField(label="Password", required=False, strip=False, widget=forms.PasswordInput(render_value=False))
    password2 = forms.CharField(label="Confirm password", required=False, strip=False, widget=forms.PasswordInput(render_value=False))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"is_active": "Active (can sign in)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        if self.instance.pk:
            profile, _ = StaffProfile.objects.get_or_create(user=self.instance)
            self.fields["role"].initial = profile.role_id
            for name in PROFILE_FIELDS:
                self.fields[name].initial = getattr(profile, name)
            self.fields["password1"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
            self.fields["password1"].help_text = password_validation.password_validators_help_text_html()

    def clean_is_active(self):
        is_active = self.cleaned_data.get("is_active")
        if self.request and self.instance.pk == self.request.user.pk and not is_active:
            raise forms.ValidationError("You cannot deactivate your own account.")
        return is_active

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "The two passwords do not match.")
            else:
                try:
                    password_validation.validate_password(password1, self.instance)
                except forms.ValidationError as error:
                    self.add_error("password1", error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self._save_m2m()
        return user

    def _save_m2m(self):
        super()._save_m2m()
        user = self.instance
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        role = self.cleaned_data["role"]
        profile.role = role
        for name in PROFILE_FIELDS:
            setattr(profile, name, self.cleaned_data.get(name))
        profile.save()
        # A person has exactly one role.
        user.groups.set([role])


def dashboard_permissions():
    """Permissions for the models shown in the dashboard, including custom ones."""
    content_types = [ContentType.objects.get_for_model(module.model) for module in site.modules()]
    return Permission.objects.filter(content_type__in=content_types).select_related("content_type")


class RoleForm(DashboardModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {"name": "Role name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = dashboard_permissions()

    def permission_groups(self):
        """Checkboxes grouped by dashboard module, in menu order."""
        checkboxes = {str(box.data["value"]): box for box in self["permissions"]}
        by_model = {}
        for perm in self.fields["permissions"].queryset:
            by_model.setdefault(perm.content_type_id, []).append(perm)

        groups = []
        for menu_group, modules in site.grouped().items():
            for module in modules:
                content_type = ContentType.objects.get_for_model(module.model)
                perms = sorted(by_model.get(content_type.pk, []), key=lambda p: permission_sort_key(p, module))
                boxes = [
                    {"box": checkboxes[str(perm.pk)], "label": permission_label(perm, module)}
                    for perm in perms
                    if str(perm.pk) in checkboxes
                ]
                if boxes:
                    groups.append({"group": menu_group, "title": module.title, "boxes": boxes})
        return groups


ACTION_ORDER = {"view": 0, "add": 1, "change": 2, "delete": 3}


def permission_sort_key(perm, module):
    action = perm.codename.split("_", 1)[0]
    if perm.codename == f"{action}_{module.model_name}":
        return (0, ACTION_ORDER.get(action, 4), perm.codename)
    return (1, 0, perm.name)


def permission_label(perm, module):
    action = perm.codename.split("_", 1)[0]
    if perm.codename == f"{action}_{module.model_name}":
        return {"view": "View", "add": "Add", "change": "Edit", "delete": "Delete"}.get(action, perm.name)
    name = perm.name[4:] if perm.name.startswith("Can ") else perm.name
    return name[:1].upper() + name[1:]


class MyProfileForm(DashboardForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=30, required=False)
    designation = forms.CharField(max_length=100, required=False)
