from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count
from django.urls import path

from apps.dashboard.registry import Module, site

from .forms import RoleForm, StaffUserForm
from .views import MyProfileView

User = get_user_model()


@site.register(User)
class StaffUserModule(Module):
    group = "Staff"
    icon = "ki-profile-user"
    name = "staff user"
    name_plural = "staff users"
    description = "People who can sign in to this dashboard. Deactivate someone instead of deleting them."
    menu_order = 10
    show_on_home = False

    list_display = ["username", "full_name", "role", "branch_names", "attends", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email", "staff_profile__phone"]
    list_filter = ["staff_profile__role", "is_active"]
    form_class = StaffUserForm
    fields = ["username", "first_name", "last_name", "email", "is_active"]
    can_delete = False

    def get_queryset(self):
        return (
            User.objects.filter(is_staff=True)
            .select_related("staff_profile__role")
            .prefetch_related("staff_profile__branches")
            .order_by("-is_active", "first_name", "username")
        )

    def get_urls(self):
        return [path("me/", MyProfileView.as_view(), name="my_profile")]

    def has_object_permission(self, user, obj, action):
        # Only a superuser may change a superuser's account, so nobody can take one over.
        return user.is_superuser or not obj.is_superuser

    def full_name(self, obj):
        return obj.get_full_name()

    full_name.short_description = "Name"

    def role(self, obj):
        profile = getattr(obj, "staff_profile", None)
        if obj.is_superuser:
            return "Superuser"
        return profile.role.name if profile and profile.role else ""

    role.short_description = "Role"

    def branch_names(self, obj):
        profile = getattr(obj, "staff_profile", None)
        if obj.is_superuser or (profile and profile.all_branches):
            return "All branches"
        return ", ".join(b.name for b in profile.branches.all()) if profile else ""

    branch_names.short_description = "Branches"

    def designation(self, obj):
        profile = getattr(obj, "staff_profile", None)
        return profile.designation if profile else ""

    designation.short_description = "Designation"

    def attends(self, obj):
        profile = getattr(obj, "staff_profile", None)
        return bool(profile and profile.can_attend)

    attends.short_description = "Attends appointments"


@site.register(Group)
class RoleModule(Module):
    group = "Staff"
    icon = "ki-security-user"
    name = "role"
    name_plural = "roles"
    description = "What each kind of staff member can see and do. Tick the permissions for the role."
    menu_order = 20
    show_on_home = False

    list_display = ["name", "member_count", "permission_count"]
    search_fields = ["name"]
    form_class = RoleForm
    fields = ["name", "permissions"]
    form_template = "accounts/role_form.html"

    def get_queryset(self):
        return Group.objects.annotate(
            members=Count("staff_profiles", distinct=True), perms=Count("permissions", distinct=True)
        ).order_by("name")

    def member_count(self, obj):
        return obj.members

    member_count.short_description = "Staff"

    def permission_count(self, obj):
        return obj.perms

    permission_count.short_description = "Permissions"
