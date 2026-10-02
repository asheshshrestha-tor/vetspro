from django import forms
from django.urls import reverse

from apps.dashboard.forms import AutocompleteSelect, DashboardForm, DashboardModelForm

from .models import BranchPrice, PackageItem, Product, ProductCategory, StockMovement, StockTransfer, StockTransferItem, TreatmentItem


def product_search(field, placeholder, url_name="product"):
    """A search-as-you-type box for choosing a product."""
    widget = AutocompleteSelect(reverse("dashboard:autocomplete", args=["shop", url_name]), placeholder=placeholder)
    widget.choices = field.choices
    widget.attrs["class"] = "form-select form-select-solid"
    field.widget = widget


def allowed_branches_for(form):
    """The branches the person filling the form works at, as a queryset for a choice field."""
    from apps.branches.context import allowed_ids
    from apps.branches.models import Branch

    return Branch.objects.filter(pk__in=allowed_ids(form.request))

PRODUCT_FIELDS = [
    "category", "name", "brand", "sku", "unit", "price", "cost_price", "is_package", "track_stock", "opening_stock",
    "low_stock_level", "treatment_kind", "default_dose", "default_route", "default_frequency", "default_duration",
    "is_prescription", "show_online", "description", "image", "is_active",
]

TREATMENT_FIELDS = [
    "treatment_kind", "name", "brand", "unit", "price", "cost_price", "default_dose", "default_route",
    "default_frequency", "default_duration", "track_stock", "opening_stock", "low_stock_level", "is_prescription",
    "category", "show_online", "description", "image", "is_active",
]

# Where a new catalogue item is filed in the shop, by what kind of treatment it is.
CATEGORY_FOR_KIND = {
    Product.MEDICINE: "Medicines",
    Product.PROCEDURE: "Clinic services",
    Product.ADVICE: "Clinic services",
}


class ProductForm(DashboardModelForm):
    opening_stock = forms.DecimalField(
        label="Opening stock", min_value=0, max_digits=10, decimal_places=2, required=False,
        help_text="How many you have now. Later changes are made from the product's Stock page.",
    )
    field_order = PRODUCT_FIELDS

    class Meta:
        model = Product
        fields = PRODUCT_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Stock only changes through logged movements once the product exists.
            del self.fields["opening_stock"]
        category = self.fields["category"]
        current = self.instance.category_id if self.instance.pk else None
        category.queryset = category.queryset.filter(is_active=True) | category.queryset.filter(pk=current)
        if "opening_stock" in self.fields:
            self.fields["opening_stock"].help_text += " It is added to the branch you are working in."
        if "is_package" in self.fields:
            self.fields["is_package"].help_text = (
                "A bundle at one price. List what is in it below; selling it takes those items from stock."
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_package"):
            # The contents are counted, not the package itself.
            cleaned["track_stock"] = False
            self.instance.track_stock = False
        return cleaned


class TreatmentItemForm(ProductForm):
    """A medicine, procedure or piece of advice vets can pick in a visit, with its usual dosing and price."""

    field_order = TREATMENT_FIELDS

    class Meta(ProductForm.Meta):
        fields = TREATMENT_FIELDS
        labels = {"price": "Price", "treatment_kind": "Type"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["treatment_kind"].required = True
        self.fields["category"].required = False
        self.fields["category"].help_text = "Shop category. Left blank, it is chosen from the type."
        self.fields["price"].help_text = "Charged per unit on the visit's bill. Use 0 for anything not charged."
        self.fields["track_stock"].help_text = "Tick for medicines you keep in stock; untick for procedures and advice."
        if not self.instance.pk:
            self.fields["track_stock"].initial = False
            self.fields["show_online"].initial = False
            self.fields["unit"].initial = "dose"

    def clean(self):
        cleaned = super().clean()
        cleaned["is_package"] = False
        kind = cleaned.get("treatment_kind")
        if kind and not cleaned.get("category"):
            name = CATEGORY_FOR_KIND[kind]
            category = ProductCategory.objects.filter(name=name).first()
            if category is None:
                category = ProductCategory.objects.create(name=name, show_online=kind == Product.MEDICINE)
            cleaned["category"] = category
        return cleaned


class PackageItemForm(DashboardModelForm):
    class Meta:
        model = PackageItem
        fields = ["component", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["component"]
        field.queryset = Product.objects.filter(is_package=False)
        product_search(field, "Search products")
        self.fields["quantity"].widget.attrs.update({"step": "any", "min": "0"})

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value is not None and value <= 0:
            raise forms.ValidationError("Must be more than zero.")
        return value


class BranchPriceForm(DashboardModelForm):
    class Meta:
        model = BranchPrice
        fields = ["product", "branch", "price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.branches.context import current_branch

        self.fields["branch"].queryset = allowed_branches_for(self)
        if not self.instance.pk:
            self.fields["branch"].initial = getattr(current_branch(self.request), "pk", None)
        product = self.fields["product"]
        product.queryset = Product.objects.filter(is_active=True) | Product.objects.filter(pk=self.instance.product_id)
        product_search(product, "Search products and services")
        self.fields["price"].help_text = "What this branch charges. Delete the row to go back to the hospital price."


class StockTransferForm(DashboardModelForm):
    class Meta:
        model = StockTransfer
        fields = ["from_branch", "to_branch", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.branches.context import current_branch
        from apps.branches.models import Branch

        # Stock is sent from a branch you work at, to any open branch.
        self.fields["from_branch"].queryset = allowed_branches_for(self)
        self.fields["to_branch"].queryset = Branch.objects.filter(is_active=True)
        if not self.instance.pk:
            self.fields["from_branch"].initial = getattr(current_branch(self.request), "pk", None)


class StockTransferItemForm(DashboardModelForm):
    class Meta:
        model = StockTransferItem
        fields = ["product", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["product"]
        field.queryset = Product.objects.filter(track_stock=True, is_active=True) | Product.objects.filter(
            pk=self.instance.product_id
        )
        product_search(field, "Search stocked products")
        self.fields["quantity"].widget.attrs.update({"step": "any", "min": "0"})

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value is not None and value <= 0:
            raise forms.ValidationError("Must be more than zero.")
        return value


class StockChangeForm(DashboardForm):
    reason = forms.ChoiceField(choices=StockMovement.MANUAL_REASONS)
    quantity = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    note = forms.CharField(max_length=255, required=False, help_text="e.g. supplier and bill number, or what was damaged.")

    ADD = {StockMovement.PURCHASE, StockMovement.RETURN}
    REMOVE = {StockMovement.DAMAGED}

    def __init__(self, *args, product, current, **kwargs):
        self.product = product
        self.current = current  # stock at the branch being changed
        super().__init__(*args, **kwargs)
        self.fields["quantity"].help_text = (
            "For a stock count correction, enter the number you counted; otherwise the number received or removed."
        )

    def change(self):
        """The signed change to apply."""
        reason, quantity = self.cleaned_data["reason"], self.cleaned_data["quantity"]
        if reason in self.ADD:
            return quantity
        if reason in self.REMOVE:
            return -quantity
        return quantity - self.current

    def clean(self):
        cleaned = super().clean()
        if "reason" in cleaned and cleaned.get("quantity") is not None:
            change = self.change()
            if change == 0:
                raise forms.ValidationError("That does not change the stock.")
            if self.current + change < 0:
                raise forms.ValidationError(f"Only {self.current.normalize():f} {self.product.unit} in stock.")
        return cleaned



class PriceSyncForm(DashboardForm):
    RESET = "reset"
    COPY = "copy"
    PROMOTE = "promote"
    ACTIONS = [
        (RESET, "Reset a branch to the hospital prices"),
        (COPY, "Copy one branch's prices to another branch"),
        (PROMOTE, "Make a branch's prices the hospital prices"),
    ]

    action = forms.ChoiceField(choices=ACTIONS, widget=forms.RadioSelect)
    branch = forms.ModelChoiceField(queryset=None, label="Branch to change", help_text="For “Make hospital prices”, the branch whose prices are used.")
    source = forms.ModelChoiceField(queryset=None, required=False, label="Copy from", help_text="Only for copying.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.branches.models import Branch

        self.fields["branch"].queryset = allowed_branches_for(self)
        self.fields["source"].queryset = Branch.objects.filter(is_active=True)
        self.fields["action"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("action") == self.COPY:
            source = cleaned.get("source")
            if source is None:
                self.add_error("source", "Choose the branch to copy from.")
            elif source == cleaned.get("branch"):
                self.add_error("source", "Choose a different branch to copy from.")
        return cleaned
