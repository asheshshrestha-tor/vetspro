from django.contrib import admin

from .models import Experience, TeamMember


class ExperienceInline(admin.TabularInline):
    model = Experience
    extra = 1


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name", "role")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ExperienceInline]
