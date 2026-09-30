from apps.dashboard.registry import Inline, Module, site

from .models import Experience, TeamMember


class ExperienceInline(Inline):
    model = Experience
    fields = ["title", "description", "order"]
    title = "Experience"


@site.register(TeamMember)
class TeamMemberModule(Module):
    icon = "ki-people"
    description = "Staff profiles shown on the team pages."
    list_display = ["photo", "name", "role", "order", "is_active"]
    search_fields = ["name", "role", "qualification"]
    list_filter = ["is_active"]
    toggle_fields = ["is_active"]
    inlines = [ExperienceInline]
