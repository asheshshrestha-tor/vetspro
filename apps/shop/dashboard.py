from django.urls import path, reverse

from apps.dashboard.registry import Action, Badge, Module, site

from . import views
from .forms import PRODUCT_FIELDS, TREATMENT_FIELDS, ProductForm, TreatmentItemForm
from .models import Product, ProductCategory, StockMovement, TreatmentItem, change_stock


def quantity(value):
    return f"{value.normalize():f}"


@site.register(Product)
class ProductModule(Module):
    group = "Shop"
    icon = "ki-basket"
    description = "Everything you sell: medicines, food, toys, cages, accessories and clinic services."
    menu_order = 10

    list_display = ["image", "name", "category", "selling_price", "stock", "show_online", "is_active"]
    search_fields = ["name", "sku", "brand", "description"]
    list_filter = ["category", "track_stock", "show_online", "is_active"]
    toggle_fields = ["show_online", "is_active"]
    form_class = ProductForm
    fields = PRODUCT_FIELDS
    per_page = 25

    def get_queryset(self):
        return Product.objects.select_related("category")

    def get_urls(self):
        return [path("<int:pk>/stock/", views.StockView.as_view(), name="product_stock")]

    def row_actions(self, obj, request):
        if not obj.track_stock:
            return []
        return [Action("Stock", reverse("dashboard:product_stock", args=[obj.pk]), icon="ki-parcel", color="light-primary")]

    def after_save(self, request, obj, form, change):
        opening = form.cleaned_data.get("opening_stock")
        if not change and opening and obj.track_stock:
            change_stock(obj, opening, StockMovement.OPENING, user=request.user)

    def badge_count(self):
        return Product.objects.low_stock().count() or None

    def autocomplete_queryset(self, request):
        return Product.objects.filter(is_active=True).select_related("category")

    def autocomplete_label(self, obj):
        label = f"{obj.name} — Rs. {obj.price:,.2f}"
        if obj.track_stock:
            label += f" · {quantity(obj.stock_quantity)} {obj.unit} in stock"
        return label

    def autocomplete_data(self, obj):
        return {
            "name": obj.name,
            "price": str(obj.price),
            "unit": obj.unit,
            "stock": str(obj.stock_quantity) if obj.track_stock else "",
        }

    def selling_price(self, obj):
        return f"Rs. {obj.price:,.2f}"

    selling_price.short_description = "Price"

    def stock(self, obj):
        if not obj.track_stock:
            return Badge("Not counted", "secondary")
        text = f"{quantity(obj.stock_quantity)} {obj.unit}"
        if obj.is_out_of_stock:
            return Badge(f"Out · {text}", "danger")
        return Badge(text, "warning" if obj.is_low_stock else "success")

    stock.short_description = "In stock"

    def home_panel(self, request):
        low = Product.objects.low_stock().select_related("category").order_by("stock_quantity")[:8]
        if not low:
            return None
        return ("shop/home_panel.html", {"products": low, "total": Product.objects.low_stock().count()})


@site.register(ProductCategory)
class ProductCategoryModule(Module):
    group = "Shop"
    icon = "ki-category"
    description = "How products are grouped, in the dashboard and the online shop."
    menu_order = 20
    show_on_home = False

    list_display = ["image", "name", "product_count", "show_online", "order", "is_active"]
    search_fields = ["name"]
    toggle_fields = ["show_online", "is_active"]
    fields = ["name", "description", "image", "show_online", "order", "is_active"]

    def product_count(self, obj):
        return obj.products.count()

    product_count.short_description = "Products"


@site.register(StockMovement)
class StockMovementModule(Module):
    group = "Shop"
    icon = "ki-arrow-up-down"
    name = "stock movement"
    name_plural = "stock history"
    description = "Every change to stock: received, sold, returned, corrected or written off."
    menu_order = 30
    show_on_home = False

    list_display = ["created_at", "product", "reason", "change", "balance_after", "invoice", "created_by"]
    search_fields = ["product__name", "note", "invoice__number"]
    list_filter = ["reason"]
    date_filter = "created_at"
    per_page = 30
    can_add = False
    can_change = False
    can_delete = False

    def get_queryset(self):
        return StockMovement.objects.select_related("product", "invoice", "created_by")

    def object_url(self, obj):
        return reverse("dashboard:product_stock", args=[obj.product_id])

    def change(self, obj):
        return Badge(f"{obj.quantity.normalize():+f}", "success" if obj.quantity > 0 else "danger")

    change.short_description = "Change"


@site.register(TreatmentItem)
class TreatmentItemModule(Module):
    group = "Clinic setup"
    icon = "ki-capsule"
    name = "treatment item"
    name_plural = "treatment catalogue"
    description = (
        "Medicines, procedures and advice vets pick in a visit's Treatment tab, with their usual dosing and price. "
        "Medicines here are the same items as in the shop, so they share one price and one stock count."
    )
    menu_order = 5
    show_on_home = False

    list_display = ["name", "kind", "charge", "usual_dosing", "stock", "is_active"]
    search_fields = ["name", "brand", "description"]
    list_filter = ["treatment_kind", "is_active"]
    toggle_fields = ["is_active"]
    form_class = TreatmentItemForm
    fields = TREATMENT_FIELDS
    per_page = 25

    def get_queryset(self):
        return TreatmentItem.objects.select_related("category").order_by("treatment_kind", "name")

    def autocomplete_queryset(self, request):
        return self.get_queryset().filter(is_active=True)

    def autocomplete_label(self, obj):
        label = f"{obj.name} · {obj.get_treatment_kind_display()}"
        if obj.price:
            label += f" · Rs. {obj.price:,.2f}"
        if obj.track_stock:
            label += f" · {quantity(obj.stock_quantity)} in stock"
        return label

    def autocomplete_data(self, obj):
        from apps.appointments.models import Treatment

        return {
            "name": obj.name,
            "kind": Treatment.KIND_FROM_CATALOGUE.get(obj.treatment_kind, "medication"),
            "price": str(obj.price),
            "unit": obj.unit,
            "dose": obj.default_dose,
            "route": obj.default_route,
            "frequency": obj.default_frequency,
            "duration": obj.default_duration,
        }

    def after_save(self, request, obj, form, change):
        opening = form.cleaned_data.get("opening_stock")
        if not change and opening and obj.track_stock:
            change_stock(obj, opening, StockMovement.OPENING, user=request.user)

    def row_actions(self, obj, request):
        if not obj.track_stock:
            return []
        return [Action("Stock", reverse("dashboard:product_stock", args=[obj.pk]), icon="ki-parcel", color="light-primary")]

    def kind(self, obj):
        colors = {Product.MEDICINE: "primary", Product.PROCEDURE: "info", Product.ADVICE: "success"}
        return Badge(obj.get_treatment_kind_display(), colors.get(obj.treatment_kind, "secondary"))

    kind.short_description = "Type"

    def charge(self, obj):
        return f"Rs. {obj.price:,.2f} / {obj.unit}" if obj.price else "No charge"

    charge.short_description = "Price"

    def usual_dosing(self, obj):
        return " · ".join(part for part in [obj.default_dose, obj.default_route, obj.default_frequency, obj.default_duration] if part)

    usual_dosing.short_description = "Usual dose"

    def stock(self, obj):
        return ProductModule.stock(self, obj)

    stock.short_description = "In stock"

