from django import forms, template

from apps.dashboard.registry import site

register = template.Library()


@register.inclusion_tag("dashboard/partials/menu.html", takes_context=True)
def dashboard_menu(context):
    request = context["request"]
    match = request.resolver_match
    current = context.get("module")

    groups = []
    for title, modules in site.grouped(request.user).items():
        items = []
        for module in modules:
            links = module.menu_items()
            # A page with its own menu link (e.g. today's queue) marks that link;
            # every other page of the module marks the module's main link.
            claimed = None
            if module is current:
                claimed = next((link for link in links if match.url_name in link["url_names"]), None)
            for link in links:
                if claimed is not None:
                    active = link is claimed
                else:
                    active = module is current and not link["url_names"]
                items.append({**link, "active": active})
        groups.append({"title": title, "items": items})
    return {"groups": groups, "is_home": match.url_name == "home"}


@register.filter
def is_checkbox(field):
    return isinstance(field.field.widget, forms.CheckboxInput)


@register.filter
def initials(user):
    name = user.get_full_name() or user.get_username()
    parts = name.split()
    letters = parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")
    return letters.upper()


@register.filter
def staff_name(user):
    if not user:
        return ""
    return user.get_full_name() or user.get_username()
