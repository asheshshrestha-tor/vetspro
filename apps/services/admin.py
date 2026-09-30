from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "icon", "is_featured", "order", "is_active")
    list_editable = ("is_featured", "order", "is_active")
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
