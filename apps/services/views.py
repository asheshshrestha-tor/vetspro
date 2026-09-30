from django.views.generic import DetailView, ListView

from .models import Service


class ServiceListView(ListView):
    template_name = "services/service_list.html"
    context_object_name = "services"

    def get_queryset(self):
        return Service.objects.active()


class ServiceDetailView(DetailView):
    template_name = "services/service_detail.html"
    context_object_name = "service"

    def get_queryset(self):
        return Service.objects.active()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["faqs"] = self.object.faqs.active()
        context["other_services"] = Service.objects.active().exclude(pk=self.object.pk)
        return context
