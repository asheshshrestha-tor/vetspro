from django.contrib import admin

from .models import PriceCategory, PriceItem


class PriceItemInline(admin.TabularInline):
    model = PriceItem
    extra = 1


@admin.register(PriceCategory)
class PriceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    list_editable = ("order", "is_active")
    inlines = [PriceItemInline]
