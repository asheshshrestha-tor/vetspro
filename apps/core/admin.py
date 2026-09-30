from django.contrib import admin

from .models import HeroSlide, SiteSettings, Stat


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Identity", {"fields": ("name", "short_name", "tagline", "description")}),
        ("Contact", {"fields": ("phone", "whatsapp", "email", "address", "opening_hours", "map_embed_url")}),
        ("Social", {"fields": ("facebook_url", "instagram_url", "tiktok_url")}),
        (
            "About page",
            {"fields": ("about_heading", "about_text", "about_image", "philosophy_text", "philosophy_image")},
        ),
        ("Visit form", {"fields": ("consent_text",)}),
        ("Invoices", {"fields": ("pan_number", "default_vat_percent", "visit_fee_item", "invoice_footer")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    list_display = ("label", "value", "suffix", "order", "is_active")
    list_editable = ("order", "is_active")
