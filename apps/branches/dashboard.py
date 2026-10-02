from django.urls import path

from apps.dashboard.forms import DashboardModelForm
from apps.dashboard.registry import Badge, Module, site

from . import views
from .models import Branch


class BranchForm(DashboardModelForm):
    class Meta:
        model = Branch
        fields = [
            "name", "code", "address", "phone", "whatsapp", "email", "opening_hours", "map_embed_url",
            "pan_number", "vat_percent", "visit_fee_item", "invoice_footer", "is_main", "is_active", "order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.shop.models import Product

        self.fields["visit_fee_item"].queryset = Product.objects.filter(is_active=True, track_stock=False)

    def clean_code(self):
        code = "".join(ch for ch in self.cleaned_data["code"] if ch.isalnum()).upper()
        if not code:
            from django import forms

            raise forms.ValidationError("Use letters and digits, e.g. CBL.")
        if Branch.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
            from django import forms

            raise forms.ValidationError("Another branch already uses this code.")
        return code


@site.register(Branch)
class BranchModule(Module):
    group = "Staff"
    icon = "ki-geolocation"
    name_plural = "branches"
    description = (
        "The hospital's branches. Visits, bills and stock belong to a branch; owners, pets, the catalogue "
        "and staff accounts are shared. Blank invoice settings use the hospital's from Site settings."
    )
    menu_order = 5
    show_on_home = False

    list_display = ["name", "code", "phone", "address", "main", "is_active"]
    search_fields = ["name", "code", "address"]
    list_filter = ["is_active"]
    form_class = BranchForm
    fields = BranchForm.Meta.fields
    can_delete = False

    def get_urls(self):
        return [path("switch/", views.SwitchBranchView.as_view(), name="branch_switch")]

    def main(self, obj):
        return Badge("Main", "primary") if obj.is_main else ""

    main.short_description = "Main"
