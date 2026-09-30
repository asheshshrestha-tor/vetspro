from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView, TemplateView

from apps.dashboard.mixins import ModuleMixin

from .forms import StockChangeForm
from .models import Product, ProductCategory, change_stock


# Dashboard

class StockView(ModuleMixin, TemplateView):
    """A product's stock: its movements, and a form to record stock received, returned or written off."""

    template_name = "shop/stock.html"

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "shop")
        kwargs.setdefault("model_name", "product")
        super().setup(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product.objects.select_related("category"), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    @property
    def can_adjust(self):
        return self.product.track_stock and self.request.user.has_perm("shop.adjust_stock")

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        form = StockChangeForm(product=self.product) if self.can_adjust else None
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        self.require(self.can_adjust)
        form = StockChangeForm(request.POST, product=self.product)
        if form.is_valid():
            try:
                change_stock(
                    self.product, form.change(), form.cleaned_data["reason"], user=request.user,
                    note=form.cleaned_data["note"],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.product.refresh_from_db()
                messages.success(
                    request, f"Stock of “{self.product}” is now {self.product.stock_quantity.normalize():f} {self.product.unit}."
                )
                return redirect("dashboard:product_stock", pk=self.product.pk)
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movements = self.product.stock_movements.select_related("invoice", "created_by")
        context.update(
            product=self.product,
            object=self.product,
            movements=Paginator(movements, 30).get_page(self.request.GET.get("page")),
            can_adjust=self.can_adjust,
        )
        return context


# Public shop

SORTS = {
    "": ("Featured", ["category__order", "name"]),
    "price": ("Price: low to high", ["price", "name"]),
    "-price": ("Price: high to low", ["-price", "name"]),
    "name": ("Name: A to Z", ["name"]),
    "new": ("Newest", ["-created_at"]),
}


def in_stock(queryset):
    return queryset.filter(Q(track_stock=False) | Q(stock_quantity__gt=0))


class ShopMixin:
    def get_categories(self):
        return (
            ProductCategory.objects.filter(is_active=True, show_online=True)
            .annotate(count=Count("products", filter=Q(products__in=Product.objects.online())))
            .filter(count__gt=0)
            .order_by("order", "name")
        )


class ProductListView(ShopMixin, ListView):
    template_name = "shop/product_list.html"
    context_object_name = "products"
    paginate_by = 24

    def get_queryset(self):
        self.category = None
        queryset = Product.objects.online().select_related("category")
        if "slug" in self.kwargs:
            self.category = get_object_or_404(ProductCategory, slug=self.kwargs["slug"], is_active=True, show_online=True)
            queryset = queryset.filter(category=self.category)
        self.query = self.request.GET.get("q", "").strip()
        if self.query:
            queryset = queryset.filter(
                Q(name__icontains=self.query) | Q(brand__icontains=self.query) | Q(description__icontains=self.query)
            )
        self.in_stock_only = self.request.GET.get("stock") == "1"
        if self.in_stock_only:
            queryset = in_stock(queryset)
        self.sort = self.request.GET.get("sort", "")
        if self.sort not in SORTS:
            self.sort = ""
        return queryset.order_by(*SORTS[self.sort][1])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            categories=self.get_categories(),
            all_count=Product.objects.online().count(),
            category=self.category,
            query=self.query,
            sort=self.sort,
            sorts=[(key, label) for key, (label, _) in SORTS.items()],
            in_stock_only=self.in_stock_only,
            crumbs=[(self.category.name, None)] if self.category else [],
        )
        return context


class ProductDetailView(ShopMixin, DetailView):
    template_name = "shop/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.online().select_related("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["crumbs"] = [
            (self.object.category.name, self.object.category.get_absolute_url()),
            (self.object.name, None),
        ]
        context["related"] = (
            in_stock(Product.objects.online().filter(category=self.object.category))
            .exclude(pk=self.object.pk)
            .select_related("category")
            .order_by("?")[:4]
        )
        return context
