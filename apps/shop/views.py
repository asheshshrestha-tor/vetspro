from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.branches.context import allowed_branches, allowed_ids, current_branch, scope_ids
from apps.dashboard.mixins import ModuleMixin

from .forms import PriceSyncForm, StockChangeForm
from .models import BranchPrice, Product, ProductCategory, StockTransfer, change_stock


# Dashboard

class StockView(ModuleMixin, TemplateView):
    """A product's stock at each branch, its movements, and a form to record stock received, returned or written off."""

    template_name = "shop/stock.html"

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "shop")
        kwargs.setdefault("model_name", "product")
        super().setup(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.product = get_object_or_404(Product.objects.select_related("category"), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    @property
    def branch(self):
        return current_branch(self.request)

    @property
    def can_adjust(self):
        # Stock is changed one branch at a time, so a branch must be chosen.
        return self.product.track_stock and self.branch is not None and self.request.user.has_perm("shop.adjust_stock")

    def stock_form(self, data=None):
        return StockChangeForm(data, product=self.product, current=self.product.stock_at(self.branch))

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        form = self.stock_form() if self.can_adjust else None
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        self.require(self.can_adjust)
        form = self.stock_form(request.POST)
        if form.is_valid():
            try:
                change_stock(
                    self.product, form.change(), form.cleaned_data["reason"], user=request.user,
                    note=form.cleaned_data["note"], branch=self.branch,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    f"Stock of “{self.product}” at {self.branch} is now "
                    f"{self.product.stock_at(self.branch).normalize():f} {self.product.unit}.",
                )
                return redirect("dashboard:product_stock", pk=self.product.pk)
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch_ids = scope_ids(self.request)
        movements = self.product.stock_movements.filter(branch_id__in=branch_ids).select_related(
            "branch", "invoice", "transfer", "created_by"
        )
        held = {row.branch_id: row for row in self.product.branch_stocks.select_related("branch")}
        rows = [
            {"branch": branch, "stock": held.get(branch.pk)}
            for branch in allowed_branches(self.request)
        ]
        shown = sum((row["stock"].quantity for row in rows if row["stock"] and row["branch"].pk in branch_ids), Decimal("0"))
        context.update(
            product=self.product,
            object=self.product,
            branch=self.branch,
            shown=shown,
            is_out=self.product.track_stock and shown <= 0,
            is_low=self.product.track_stock and shown <= self.product.low_stock_level,
            branch_rows=rows if len(rows) > 1 else [],
            price_here=self.product.price_at(self.branch),
            movements=Paginator(movements, 30).get_page(self.request.GET.get("page")),
            show_branch=len(branch_ids) > 1,
            can_adjust=self.can_adjust,
            can_transfer=self.product.track_stock and self.request.user.has_perm("shop.add_stocktransfer") and len(rows) > 1,
        )
        return context


class PriceSyncView(ModuleMixin, TemplateView):
    """Bring branch prices back in line: copy one branch's prices to another, or reset to the hospital price."""

    template_name = "shop/price_sync.html"

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "shop")
        kwargs.setdefault("model_name", "branchprice")
        super().setup(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.require(self.module.user_can_change(request.user) or self.module.user_can_delete(request.user))
        return self.render_to_response(self.get_context_data(form=PriceSyncForm(request=request)))

    def post(self, request, *args, **kwargs):
        user = request.user
        self.require(self.module.user_can_change(user) and self.module.user_can_delete(user))
        form = PriceSyncForm(request.POST, request=request)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        data = form.cleaned_data
        action, target = data["action"], data["branch"]
        with transaction.atomic():
            if action == PriceSyncForm.RESET:
                count, _ = BranchPrice.objects.filter(branch=target).delete()
                message = f"{target} now sells everything at the hospital price ({count} own price{'s' if count != 1 else ''} removed)."
            elif action == PriceSyncForm.COPY:
                source = data["source"]
                BranchPrice.objects.filter(branch=target).exclude(
                    product_id__in=BranchPrice.objects.filter(branch=source).values("product_id")
                ).delete()
                count = 0
                for row in BranchPrice.objects.filter(branch=source):
                    BranchPrice.objects.update_or_create(product_id=row.product_id, branch=target, defaults={"price": row.price})
                    count += 1
                message = f"{target} now has the same prices as {source} ({count} own price{'s' if count != 1 else ''})."
            else:
                self.require(user.has_perm("shop.change_product"))
                count = 0
                for row in BranchPrice.objects.filter(branch=target).select_related("product"):
                    Product.objects.filter(pk=row.product_id).update(price=row.price)
                    count += 1
                # Other branches that matched the new hospital price no longer need their own row.
                BranchPrice.objects.filter(branch=target).delete()
                for row in BranchPrice.objects.select_related("product"):
                    if row.price == row.product.price:
                        row.delete()
                message = f"{count} hospital price{'s' if count != 1 else ''} updated from {target}."
        messages.success(request, message)
        return redirect(self.module.list_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["counts"] = [
            (branch, BranchPrice.objects.filter(branch=branch).count()) for branch in allowed_branches(self.request)
        ]
        return context


def transfer_actions(transfer, request):
    """Buttons for what this person may do with the transfer now."""
    user = request.user
    ids = set(allowed_ids(request))
    actions = []

    def add(action, label, icon, color, confirm=""):
        actions.append({
            "action": action, "label": label, "icon": icon, "color": color, "confirm": confirm,
            "url": reverse("dashboard:stocktransfer_action", args=[transfer.pk, action]),
        })

    if transfer.status == StockTransfer.DRAFT and transfer.from_branch_id in ids and user.has_perm("shop.change_stocktransfer"):
        add("send", "Send", "ki-send", "primary", f"Send {transfer.number}? The items leave {transfer.from_branch}'s stock now.")
    if transfer.status == StockTransfer.SENT and transfer.to_branch_id in ids and user.has_perm("shop.receive_stocktransfer"):
        add("receive", "Receive", "ki-check-circle", "success", f"Mark {transfer.number} as received at {transfer.to_branch}?")
    if transfer.status in (StockTransfer.DRAFT, StockTransfer.SENT) and transfer.from_branch_id in ids and user.has_perm(
        "shop.change_stocktransfer"
    ):
        message = "Cancel this transfer?" + (" The items go back to the sending branch." if transfer.status == StockTransfer.SENT else "")
        add("cancel", "Cancel", "ki-cross-circle", "light-danger", message)
    return actions


class TransferActionView(ModuleMixin, View):
    http_method_names = ["post"]

    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "shop")
        kwargs.setdefault("model_name", "stocktransfer")
        super().setup(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        transfer = get_object_or_404(self.module.access_queryset(request), pk=kwargs["pk"])
        action = kwargs["action"]
        allowed = {item["action"] for item in transfer_actions(transfer, request)}
        self.require(action in allowed)
        try:
            getattr(transfer, action)(request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            done = {"send": "sent", "receive": "received", "cancel": "cancelled"}[action]
            messages.success(request, f"Transfer {transfer.number} {done}.")
        return redirect(transfer.get_absolute_url())


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
        from apps.branches.models import Branch

        held = dict(self.object.branch_stocks.values_list("branch_id", "quantity"))
        context["branch_stock"] = [
            {"branch": branch, "available": held.get(branch.pk, 0) > 0}
            for branch in Branch.objects.filter(is_active=True)
        ]
        context["price_varies"] = self.object.branch_prices.exclude(price=self.object.price).exists()
        context["related"] = (
            in_stock(Product.objects.online().filter(category=self.object.category))
            .exclude(pk=self.object.pk)
            .select_related("category")
            .order_by("?")[:4]
        )
        return context
