from django.contrib import admin

from .models import FAQ, FAQCategory


class FAQInline(admin.StackedInline):
    model = FAQ
    extra = 1


@admin.register(FAQCategory)
class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    list_editable = ("order", "is_active")
    inlines = [FAQInline]


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "service", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("category", "service")
    search_fields = ("question", "answer")
