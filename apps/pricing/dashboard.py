from apps.dashboard.registry import Inline, Module, site

from .models import PriceCategory, PriceItem


class PriceItemInline(Inline):
    model = PriceItem
    fields = ["name", "description", "price", "is_starting_price", "order", "is_active"]
    title = "Price items"


@site.register(PriceCategory)
class PriceCategoryModule(Module):
    icon = "ki-price-tag"
    description = "Price list groups and the items in each one."
    list_display = ["image", "name", "item_count", "order", "is_active"]
    search_fields = ["name", "description"]
    toggle_fields = ["is_active"]
    inlines = [PriceItemInline]

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Items"
