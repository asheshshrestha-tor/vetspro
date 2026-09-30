from apps.dashboard.registry import Module, site

from .models import HeroSlide, SiteSettings, Stat


@site.register(SiteSettings)
class SiteSettingsModule(Module):
    group = "Website"
    icon = "ki-setting-2"
    description = "The hospital's contact details, social links and about text."
    singleton = True


@site.register(HeroSlide)
class HeroSlideModule(Module):
    group = "Website"
    icon = "ki-slider"
    description = "The slides at the top of the home page."
    list_display = ["image", "title", "subtitle", "order", "is_active"]
    search_fields = ["title", "subtitle"]
    toggle_fields = ["is_active"]


@site.register(Stat)
class StatModule(Module):
    group = "Website"
    icon = "ki-chart-simple"
    description = "The numbers band on the home and about pages."
    list_display = ["label", "value", "suffix", "order", "is_active"]
    toggle_fields = ["is_active"]
