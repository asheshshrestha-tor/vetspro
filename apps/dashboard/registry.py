"""Registry of the models that are managed from the dashboard.

An app adds its models by creating a ``dashboard.py`` file:

    from apps.dashboard.registry import Module, site

    @site.register(Service)
    class ServiceModule(Module):
        icon = "ki-heart-circle"
        list_display = ["title", "is_active"]
"""
from functools import reduce
from operator import or_

from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.urls import reverse

# Menu groups in this order; groups not listed here follow in registration order.
DEFAULT_GROUP_ORDER = ["Clinic", "Billing", "Shop", "Clinic setup", "Website", "Content", "Inbox", "Staff"]


class Inline:
    """Child rows edited on the parent's form, e.g. the items of a price category."""

    model = None
    fields = []
    title = ""
    extra = 1
    form_class = None
    fk_name = None  # when the child has more than one link to the parent

    def get_title(self):
        return self.title or self.model._meta.verbose_name_plural.capitalize()


class Badge:
    """A coloured label in a list or detail cell. Colours are theme names: primary, success, danger..."""

    def __init__(self, label, color="primary"):
        self.label = label
        self.color = color

    def __str__(self):
        return str(self.label)


class Action:
    """A button on a list row. POST actions are sent as a form so they carry the CSRF token."""

    def __init__(self, label, url, icon="", color="light-primary", post=False, confirm=""):
        self.label = label
        self.url = url
        self.icon = icon
        self.color = color
        self.post = post
        self.confirm = confirm


class Module:
    model = None

    group = "Content"
    icon = "ki-element-11"
    description = ""
    # Overrides for the model's verbose names, e.g. "staff user" for Django's User.
    name = ""
    name_plural = ""
    # Sort position inside the menu group; equal values keep registration order.
    menu_order = 100
    show_on_home = True

    list_display = []
    search_fields = []
    # Field names or lookups through relations, e.g. "pet__species".
    # Model field lookups, or names of module methods `(request, queryset, value)` with a
    # `filter_choices` attribute for filters that are not a plain field.
    list_filter = []
    # A date field to filter the list by, with quick ranges such as today and this week.
    date_filter = ""
    ordering = None
    per_page = 15

    fields = None
    form_class = None
    inlines = []
    # Foreign keys picked with a search-as-you-type box instead of a full dropdown.
    autocomplete_fields = []
    # Request parameters the autocomplete endpoint may filter on, e.g. ["client"] for pets.
    autocomplete_filters = []
    # Boolean fields that can be switched on and off straight from the list.
    toggle_fields = []

    # Where the record's branch is, e.g. "branch" or "appointment__branch". Records of a
    # module with a branch are only listed for the branch being worked in, and only
    # opened by people who work at their branch. Blank means shared by all branches.
    branch_field = ""
    # Records without a branch (e.g. a website message) are shown in every branch.
    branch_optional = False

    # Custom templates for the generic pages.
    list_template = ""
    form_template = ""
    detail_template = ""

    # Replacement views for the generic "list", "add" and "edit" pages.
    views = {}

    # A singleton has exactly one row, so its menu link opens the form directly.
    singleton = False
    can_add = True
    can_change = True
    can_delete = True

    def __init__(self, model):
        self.model = model
        self.opts = model._meta

    @property
    def app_label(self):
        return self.opts.app_label

    @property
    def model_name(self):
        return self.opts.model_name

    @property
    def key(self):
        return f"{self.app_label}.{self.model_name}"

    @property
    def singular(self):
        return str(self.name or self.opts.verbose_name)

    @property
    def plural(self):
        return str(self.name_plural or self.opts.verbose_name_plural)

    @property
    def title(self):
        name = self.singular if self.singleton else self.plural
        return name[:1].upper() + name[1:]

    def get_queryset(self):
        queryset = self.model._default_manager.all()
        if self.ordering:
            queryset = queryset.order_by(*self.ordering)
        return queryset

    def search_conditions(self, term):
        """Conditions for the search box, combined with OR. Extend to match values stored differently."""
        return [Q(**{f"{name}__icontains": term}) for name in self.search_fields]

    def apply_search(self, queryset, term):
        conditions = self.search_conditions(term) if term else []
        if not conditions:
            return queryset
        return queryset.filter(reduce(or_, conditions)).distinct()

    def autocomplete_queryset(self, request):
        queryset = self.queryset_for(request)
        if any(f.name == "is_active" for f in self.opts.fields):
            queryset = queryset.filter(is_active=True)
        return queryset

    def autocomplete_label(self, obj, request=None):
        return str(obj)

    def autocomplete_data(self, obj, request=None):
        """Extra values sent with each search result, e.g. a product's price."""
        return {}

    def branch_condition(self, ids):
        """Which rows belong to these branches. None means the module is not split by branch."""
        if not self.branch_field:
            return None
        condition = Q(**{f"{self.branch_field}__in": ids})
        if self.branch_optional:
            condition |= Q(**{f"{self.branch_field}__isnull": True})
        return condition

    def _branch_filter(self, queryset, ids):
        condition = self.branch_condition(list(ids))
        return queryset if condition is None else queryset.filter(condition)

    def queryset_for(self, request):
        """Records listed for the branch being worked in (or all of the person's branches)."""
        from apps.branches.context import scope_ids

        return self._branch_filter(self.get_queryset(), scope_ids(request))

    def access_queryset(self, request):
        """Records this person may open: those at any branch they work at."""
        from apps.branches.context import allowed_ids

        return self._branch_filter(self.get_queryset(), allowed_ids(request))

    def assign_branch(self, request, obj):
        """New records of a module with a branch are created in the branch being worked in."""
        if self.branch_field == "branch" and getattr(obj, "branch_id", None) is None:
            from apps.branches.context import require_branch

            obj.branch = require_branch(request)

    def get_singleton(self):
        return self.model.load()

    def get_fields(self):
        if self.fields is not None:
            return list(self.fields)
        names = [f.name for f in self.opts.fields if f.editable and not f.auto_created]
        # Ordering and visibility are housekeeping, so they follow the content fields.
        last = [name for name in ("order", "is_active") if name in names]
        return [name for name in names if name not in last] + last

    def form_kwargs(self, request, obj):
        """Extra keyword arguments for the module's form."""
        return {}

    def save_model(self, request, obj, form, change):
        """Called before the object is saved; set audit fields here."""

    def after_save(self, request, obj, form, change):
        """Called once the object and its inline rows are saved."""

    def badge_count(self, request=None):
        """Number shown next to the module in the menu. None shows nothing."""
        return None

    def menu_items(self, request=None):
        """Links shown in the side menu. Extra items can point at the module's own pages."""
        return [{"title": self.title, "url": self.list_url, "icon": self.icon, "badge": self.badge_count(request), "url_names": []}]

    def row_actions(self, obj, request):
        """Extra buttons for a row in the list."""
        return []

    def object_url(self, obj):
        return self.url("edit", obj.pk)

    def home_panel(self, request):
        """A (template name, context) pair to show on the dashboard home page, or None."""
        return None

    def get_urls(self):
        """Extra pages, mounted under /dashboard/<app_label>/<model_name>/."""
        return []

    def on_view(self, obj):
        """Called when a read-only record is opened."""

    # Permissions follow Django's model permissions, so they are managed per user or group.
    def _has_perm(self, user, action):
        codename = get_permission_codename(action, self.opts)
        return user.has_perm(f"{self.app_label}.{codename}")

    def can_view(self, user):
        return self._has_perm(user, "view") or self._has_perm(user, "change")

    def user_can_add(self, user):
        return self.can_add and not self.singleton and self._has_perm(user, "add")

    def user_can_change(self, user):
        return self.can_change and self._has_perm(user, "change")

    def user_can_toggle(self, user):
        # Switching a flag is allowed even where the full form is not, e.g. marking a message as read.
        return bool(self.toggle_fields) and self._has_perm(user, "change")

    def user_can_delete(self, user):
        return self.can_delete and not self.singleton and self._has_perm(user, "delete")

    def extra_context(self, request, obj):
        """More template context for the record's form or detail page."""
        return {}

    def has_object_permission(self, user, obj, action):
        """Per-record rule on top of the model permissions. action is "change" or "delete"."""
        return True

    def url(self, name, *args):
        return reverse(f"dashboard:{name}", args=[self.app_label, self.model_name, *args])

    @property
    def list_url(self):
        return self.url("list")

    @property
    def add_url(self):
        return self.url("add")

    @property
    def autocomplete_url(self):
        return self.url("autocomplete")


class DashboardSite:
    def __init__(self):
        self._modules = {}

    def register(self, model, module_class=None):
        def wrap(cls):
            module = cls(model)
            if module.key in self._modules:
                raise ImproperlyConfigured(f"{module.key} is already registered with the dashboard.")
            if not module.singleton and not module.list_display:
                raise ImproperlyConfigured(f"{cls.__name__} must define list_display.")
            self._modules[module.key] = module
            return cls

        if module_class is not None:
            return wrap(module_class)
        return wrap

    def get(self, app_label, model_name):
        return self._modules.get(f"{app_label}.{model_name}")

    def for_model(self, model):
        return self._modules.get(f"{model._meta.app_label}.{model._meta.model_name}")

    def modules(self, user=None):
        modules = self._modules.values()
        if user is not None:
            modules = [m for m in modules if m.can_view(user)]
        return list(modules)

    def grouped(self, user=None):
        """Modules keyed by menu group, in menu order; only those the user may see when a user is given."""
        order = list(getattr(settings, "DASHBOARD_MENU_GROUPS", DEFAULT_GROUP_ORDER))
        groups = {}
        for module in self.modules(user):
            groups.setdefault(module.group, []).append(module)
        for group in groups:
            if group not in order:
                order.append(group)
        return {
            group: sorted(groups[group], key=lambda m: m.menu_order)
            for group in sorted(groups, key=order.index)
        }


site = DashboardSite()
