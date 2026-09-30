from django.db.models import Prefetch
from django.views.generic import ListView

from .models import PriceCategory, PriceItem


class PricingView(ListView):
    template_name = "pricing/pricing.html"
    context_object_name = "categories"

    def get_queryset(self):
        return PriceCategory.objects.active().prefetch_related(
            Prefetch("items", queryset=PriceItem.objects.active())
        )
