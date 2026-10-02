from django.db.models import DecimalField, OuterRef, Q, Subquery
from django.urls import path, reverse

from apps.branches.context import allowed_ids, current_branch, scope_ids
from apps.dashboard.registry import Action, Badge, Inline, Module, site

from . import views
from .forms import (
    PRODUCT_FIELDS,
    TREATMENT_FIELDS,
    BranchPriceForm,
    PackageItemForm,
    ProductForm,
    StockTransferForm,
    StockTransferItemForm,
    TreatmentItemForm,
)
from .models import (
    BranchPrice,
    BranchStock,
    PackageItem,
    Product,
    ProductCategory,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    TreatmentItem,
    change_stock,
)


def quantity(value):
    return f"{value.normalize():f}"


def with_branch_price(queryset, branch):
    """Annotate `branch_price`: the branch's own price, or None when it follows the hospital price."""
    if branch is None:
        return queryset
    prices = BranchPrice.objects.filter(product=OuterRef("pk"), branch=branch).values("price")[:1]
    return queryset.annotate(branch_price=Subquery(prices, output_field=DecimalField(max_digits=10, decimal_places=2)))


def selling_price(obj):
    override = getattr(obj, "branch_price", None)
    return obj.price if override is None else override


def add_opening_stock(request, obj, form, change):
    opening = form.cleaned_data.get("opening_stock")
    if not change and opening and obj.track_stock:
        change_stock(obj, opening, StockMovement.OPENING, user=request.user, branch=current_branch(request))


class StockColumns:
    """Stock and price columns that follow the branch being worked in."""

    def queryset_for(self, request):
        queryset = super().queryset_for(request).with_stock(scope_ids(request))
        return with_branch_price(queryset, current_branch(request))

    def selling_price(self, obj):
        price = selling_price(obj)
        text = f"Rs. {price:,.2f}"
        if price != obj.price:
            return Badge(f"{text} (hospital Rs. {obj.price:,.2f})", "info")
        return text

    selling_price.short_description = "Price"

    def stock(self, obj):
        if obj.is_package:
            return Badge("Package", "info")
        if not obj.track_stock:
            return Badge("Not counted", "secondary")
        text = f"{quantity(obj.shown_stock)} {obj.unit}"
        if obj.is_out_of_stock:
            return Badge(f"Out · {text}", "danger")
        return Badge(text, "warning" if obj.is_low_stock else "success")

    stock.short_description = "In stock"

    def row_actions(self, obj, request):
        if not obj.track_stock:
            return []
        return [Action("Stock", reverse("dashboard:product_stock", args=[obj.pk]), icon="ki-parcel", color="light-primary")]


class PackageItemInline(Inline):
    model = PackageItem
    fields = ["component", "quantity"]
    title = "In this package"
    form_class = PackageItemForm
    fk_name = "package"


@site.register(Product)
class ProductModule(StockColumns, Module):
    group = "Shop"
    icon = "ki-basket"
    description = "Everything you sell: medicines, food, toys, cages, accessories, packages and clinic services."
    menu_order = 10

    list_display = ["image", "name", "category", "selling_price", "stock", "show_online", "is_active"]
    search_fields = ["name", "sku", "brand", "description"]
    list_filter = ["category", "track_stock", "is_package", "show_online", "is_active"]
    toggle_fields = ["show_online", "is_active"]
    form_class = ProductForm
    fields = PRODUCT_FIELDS
    inlines = [PackageItemInline]
    per_page = 25

    def get_queryset(self):
        return Product.objects.select_related("category")

    def get_urls(self):
        return [path("<int:pk>/stock/", views.StockView.as_view(), name="product_stock")]

    def after_save(self, request, obj, form, change):
        add_opening_stock(request, obj, form, change)

    def badge_count(self, request=None):
        if request is None:
            return None
        return Product.objects.low_stock(scope_ids(request)).count() or None

    def autocomplete_queryset(self, request):
        queryset = Product.objects.filter(is_active=True).select_related("category").with_stock(scope_ids(request))
        return with_branch_price(queryset, current_branch(request))

    def autocomplete_label(self, obj, request=None):
        label = f"{obj.name} — Rs. {selling_price(obj):,.2f}"
        if obj.is_package:
            label += " · package"
        elif obj.track_stock:
            label += f" · {quantity(obj.shown_stock)} {obj.unit} in stock"
        return label

    def autocomplete_data(self, obj, request=None):
        return {
            "name": obj.name,
            "price": str(selling_price(obj)),
            "unit": obj.unit,
            "stock": f"{obj.shown_stock:.2f}" if obj.track_stock and not obj.is_package else "",
        }

    def home_panel(self, request):
        low = BranchStock.objects.low(scope_ids(request))
        if not low.exists():
            return None
        return (
            "shop/home_panel.html",
            {
                "rows": low.select_related("product", "branch").order_by("quantity", "product__name")[:8],
                "total": low.count(),
                "show_branch": len(scope_ids(request)) > 1,
            },
        )


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


@site.register(BranchPrice)
class BranchPriceModule(Module):
    group = "Shop"
    icon = "ki-price-tag"
    name = "branch price"
    name_plural = "branch prices"
    description = (
        "Prices that differ at a branch. Anything not listed here sells at the hospital price. "
        "Use Sync prices to copy prices between branches or reset them."
    )
    menu_order = 25
    show_on_home = False
    branch_field = "branch"

    list_display = ["product", "branch", "branch_price", "hospital_price", "difference"]
    search_fields = ["product__name", "product__sku"]
    list_filter = ["branch", "product__category"]
    form_class = BranchPriceForm
    fields = ["product", "branch", "price"]
    per_page = 30

    def get_queryset(self):
        return BranchPrice.objects.select_related("product", "branch")

    def get_urls(self):
        return [path("sync/", views.PriceSyncView.as_view(), name="branchprice_sync")]

    def menu_items(self, request=None):
        return super().menu_items(request) + [
            {
                "title": "Sync prices",
                "url": reverse("dashboard:branchprice_sync"),
                "icon": "ki-arrows-loop",
                "badge": None,
                "url_names": ["branchprice_sync"],
            }
        ]

    def row_actions(self, obj, request):
        if not self.user_can_delete(request.user):
            return []
        return [
            Action("Use hospital price", reverse("dashboard:delete", args=["shop", "branchprice", obj.pk]),
                   icon="ki-arrows-circle", color="light")
        ]

    def branch_price(self, obj):
        return f"Rs. {obj.price:,.2f}"

    branch_price.short_description = "Branch price"

    def hospital_price(self, obj):
        return f"Rs. {obj.product.price:,.2f}"

    hospital_price.short_description = "Hospital price"

    def difference(self, obj):
        change = obj.price - obj.product.price
        if not change:
            return Badge("Same", "secondary")
        return Badge(f"{change:+,.2f}", "warning" if change > 0 else "info")

    difference.short_description = "Difference"


@site.register(StockMovement)
class StockMovementModule(Module):
    group = "Shop"
    icon = "ki-arrow-up-down"
    name = "stock movement"
    name_plural = "stock history"
    description = "Every change to stock: received, sold, returned, moved between branches, corrected or written off."
    menu_order = 30
    show_on_home = False
    branch_field = "branch"

    list_display = ["created_at", "product", "branch", "reason", "change", "balance_after", "reference", "created_by"]
    search_fields = ["product__name", "note", "invoice__number", "transfer__number"]
    list_filter = ["reason", "branch"]
    date_filter = "created_at"
    per_page = 30
    can_add = False
    can_change = False
    can_delete = False

    def get_queryset(self):
        return StockMovement.objects.select_related("product", "branch", "invoice", "transfer", "created_by")

    def object_url(self, obj):
        return reverse("dashboard:product_stock", args=[obj.product_id])

    def change(self, obj):
        return Badge(f"{obj.quantity.normalize():+f}", "success" if obj.quantity > 0 else "danger")

    change.short_description = "Change"

    def reference(self, obj):
        if obj.invoice_id:
            return obj.invoice.display_number
        if obj.transfer_id:
            return obj.transfer.number
        return obj.note

    reference.short_description = "Reference"


class StockTransferItemInline(Inline):
    model = StockTransferItem
    fields = ["product", "quantity"]
    title = "Items"
    form_class = StockTransferItemForm
    extra = 3


@site.register(StockTransfer)
class StockTransferModule(Module):
    group = "Shop"
    icon = "ki-delivery"
    name = "stock transfer"
    name_plural = "stock transfers"
    description = "Stock sent between branches. It leaves the sending branch when sent and arrives when received."
    menu_order = 35
    show_on_home = False

    list_display = ["number", "created_at", "from_branch", "to_branch", "item_count", "status_badge"]
    search_fields = ["number", "note"]
    list_filter = ["status", "from_branch", "to_branch"]
    date_filter = "created_at"
    form_class = StockTransferForm
    fields = ["from_branch", "to_branch", "note"]
    inlines = [StockTransferItemInline]
    form_template = "shop/transfer_form.html"
    detail_template = "shop/transfer_detail.html"
    per_page = 25

    def get_queryset(self):
        return StockTransfer.objects.select_related("from_branch", "to_branch").prefetch_related("items")

    def branch_condition(self, ids):
        # A transfer belongs to both ends.
        return Q(from_branch_id__in=ids) | Q(to_branch_id__in=ids)

    def get_urls(self):
        return [path("<int:pk>/<str:action>/", views.TransferActionView.as_view(), name="stocktransfer_action")]

    def badge_count(self, request=None):
        if request is None:
            return None
        return StockTransfer.objects.filter(status=StockTransfer.SENT, to_branch_id__in=scope_ids(request)).count() or None

    def has_object_permission(self, user, obj, action):
        # Only drafts are edited or deleted; once sent, a transfer is received or cancelled.
        if action in ("change", "delete"):
            return obj.status == StockTransfer.DRAFT
        return True

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

    def extra_context(self, request, obj):
        if obj is None:
            return {}
        return {"transfer_actions": views.transfer_actions(obj, request)}

    def item_count(self, obj):
        return len(obj.items.all())

    item_count.short_description = "Items"

    def status_badge(self, obj):
        return Badge(obj.get_status_display(), obj.status_color)

    status_badge.short_description = "Status"

    def row_actions(self, obj, request):
        return [
            Action(item["label"], item["url"], icon=item["icon"], color=item["color"], post=True, confirm=item["confirm"])
            for item in views.transfer_actions(obj, request)
        ]


@site.register(TreatmentItem)
class TreatmentItemModule(StockColumns, Module):
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
        queryset = self.get_queryset().filter(is_active=True).with_stock(scope_ids(request))
        return with_branch_price(queryset, current_branch(request))

    def autocomplete_label(self, obj, request=None):
        label = f"{obj.name} · {obj.get_treatment_kind_display()}"
        price = selling_price(obj)
        if price:
            label += f" · Rs. {price:,.2f}"
        if obj.track_stock:
            label += f" · {quantity(obj.shown_stock)} in stock"
        return label

    def autocomplete_data(self, obj, request=None):
        from apps.appointments.models import Treatment

        return {
            "name": obj.name,
            "kind": Treatment.KIND_FROM_CATALOGUE.get(obj.treatment_kind, "medication"),
            "price": str(selling_price(obj)),
            "unit": obj.unit,
            "dose": obj.default_dose,
            "route": obj.default_route,
            "frequency": obj.default_frequency,
            "duration": obj.default_duration,
        }

    def after_save(self, request, obj, form, change):
        add_opening_stock(request, obj, form, change)

    def kind(self, obj):
        colors = {Product.MEDICINE: "primary", Product.PROCEDURE: "info", Product.ADVICE: "success"}
        return Badge(obj.get_treatment_kind_display(), colors.get(obj.treatment_kind, "secondary"))

    kind.short_description = "Type"

    def charge(self, obj):
        price = selling_price(obj)
        return f"Rs. {price:,.2f} / {obj.unit}" if price else "No charge"

    charge.short_description = "Price"

    def usual_dosing(self, obj):
        return " · ".join(part for part in [obj.default_dose, obj.default_route, obj.default_frequency, obj.default_duration] if part)

    usual_dosing.short_description = "Usual dose"
