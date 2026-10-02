from django import forms
from django.forms import inlineformset_factory
from django.urls import reverse

from apps.clients.models import Client
from apps.dashboard.forms import AutocompleteSelect, DashboardForm, DashboardModelForm, style_fields
from apps.shop.models import Product

from .models import Invoice, InvoiceItem, Payment


def autocomplete(field, app_label, model_name, placeholder, forward=()):
    """Turn a model choice field into a search-as-you-type box."""
    widget = AutocompleteSelect(
        reverse("dashboard:autocomplete", args=[app_label, model_name]), forward=forward, placeholder=placeholder
    )
    widget.choices = field.choices
    widget.attrs["class"] = "form-select form-select-solid"
    field.widget = widget


class CustomerFields:
    """Either an existing client, or just a name and phone for a one-off buyer."""

    def setup_customer(self):
        autocomplete(self.fields["client"], "clients", "client", "Search clients by name or phone (optional)")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("client"):
            cleaned["customer_name"] = ""
            cleaned["customer_phone"] = ""
        return cleaned


class NewSaleForm(CustomerFields, DashboardForm):
    client = forms.ModelChoiceField(queryset=Client.objects.filter(is_active=True), required=False, label="Client")
    customer_name = forms.CharField(max_length=150, required=False, label="Or customer name")
    customer_phone = forms.CharField(max_length=30, required=False, label="Phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_customer()
        self.fields["customer_name"].help_text = "Leave both blank for an anonymous counter sale."


class InvoiceForm(CustomerFields, DashboardModelForm):
    class Meta:
        model = Invoice
        fields = ["client", "customer_name", "customer_phone", "discount", "vat_percent", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.appointment_id:
            # A visit's bill always goes to the pet's owner.
            for name in ("client", "customer_name", "customer_phone"):
                del self.fields[name]
        else:
            self.fields["client"].queryset = Client.objects.filter(is_active=True) | Client.objects.filter(
                pk=self.instance.client_id
            )
            self.setup_customer()
        self.fields["discount"].min_value = 0
        self.fields["vat_percent"].min_value = 0
        self.fields["vat_percent"].max_value = 100

    def clean_discount(self):
        discount = self.cleaned_data.get("discount") or 0
        if discount < 0:
            raise forms.ValidationError("The discount cannot be negative.")
        return discount


class InvoiceItemForm(DashboardModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["product", "description", "quantity", "unit_price", "discount_percent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product = self.fields["product"]
        product.required = False
        product.queryset = Product.objects.filter(is_active=True) | Product.objects.filter(pk=self.instance.product_id)
        autocomplete(product, "shop", "product", "Search products and services")
        self.fields["description"].required = False
        self.fields["description"].widget.attrs["placeholder"] = "Description (filled in from the product)"
        self.fields["unit_price"].required = False
        self.fields["quantity"].widget.attrs.update({"step": "any", "min": "0"})
        self.fields["unit_price"].widget.attrs.update({"step": "any", "min": "0"})
        self.fields["discount_percent"].required = False
        self.fields["discount_percent"].widget.attrs.update({"step": "any", "min": "0", "max": "100", "placeholder": "0"})
        style_fields(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        product = cleaned.get("product")
        if product is not None:
            if not cleaned.get("description"):
                cleaned["description"] = product.name
            if cleaned.get("unit_price") is None:
                branch = getattr(self.instance.invoice, "branch", None) if self.instance.invoice_id else None
                cleaned["unit_price"] = product.price_at(branch)
        else:
            if not cleaned.get("description"):
                self.add_error("description", "Choose a product or describe the item.")
            if cleaned.get("unit_price") is None:
                self.add_error("unit_price", "Enter the price.")
        quantity = cleaned.get("quantity")
        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Must be more than zero.")
        if cleaned.get("unit_price") is not None and cleaned["unit_price"] < 0:
            self.add_error("unit_price", "Cannot be negative.")
        discount = cleaned.get("discount_percent")
        if discount is None:
            cleaned["discount_percent"] = 0
        elif not 0 <= discount <= 100:
            self.add_error("discount_percent", "Between 0 and 100.")
        return cleaned

    def _post_clean(self):
        # Fill the model from the defaults worked out in clean() before it is validated.
        for name in ("description", "unit_price", "discount_percent"):
            if name in self.cleaned_data:
                setattr(self.instance, name, self.cleaned_data[name])
        super()._post_clean()


InvoiceItemFormSet = inlineformset_factory(
    Invoice, InvoiceItem, form=InvoiceItemForm, extra=1, can_delete=True, min_num=0
)


class PaymentForm(DashboardModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "reference"]

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        if invoice is not None:
            self.fields["amount"].initial = invoice.balance
        self.fields["amount"].widget.attrs.update({"step": "any", "min": "0"})
