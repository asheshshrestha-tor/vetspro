from django.db.models import Prefetch
from django.views.generic import ListView

from .models import FAQ, FAQCategory


class FAQListView(ListView):
    template_name = "faq/faq_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return FAQCategory.objects.active().prefetch_related(Prefetch("faqs", queryset=FAQ.objects.active()))
