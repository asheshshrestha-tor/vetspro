from django import forms

from apps.dashboard.forms import DashboardForm, DashboardModelForm

from .models import Product, ProductCategory, StockMovement, TreatmentItem

PRODUCT_FIELDS = [
    "category", "name", "brand", "sku", "unit", "price", "cost_price", "track_stock", "opening_stock",
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
        kind = cleaned.get("treatment_kind")
        if kind and not cleaned.get("category"):
            name = CATEGORY_FOR_KIND[kind]
            category = ProductCategory.objects.filter(name=name).first()
            if category is None:
                category = ProductCategory.objects.create(name=name, show_online=kind == Product.MEDICINE)
            cleaned["category"] = category
        return cleaned


class StockChangeForm(DashboardForm):
    reason = forms.ChoiceField(choices=StockMovement.MANUAL_REASONS)
    quantity = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    note = forms.CharField(max_length=255, required=False, help_text="e.g. supplier and bill number, or what was damaged.")

    ADD = {StockMovement.PURCHASE, StockMovement.RETURN}
    REMOVE = {StockMovement.DAMAGED}

    def __init__(self, *args, product, **kwargs):
        self.product = product
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
        return quantity - self.product.stock_quantity

    def clean(self):
        cleaned = super().clean()
        if "reason" in cleaned and cleaned.get("quantity") is not None:
            change = self.change()
            if change == 0:
                raise forms.ValidationError("That does not change the stock.")
            if self.product.stock_quantity + change < 0:
                raise forms.ValidationError(
                    f"Only {self.product.stock_quantity.normalize():f} {self.product.unit} in stock."
                )
        return cleaned

