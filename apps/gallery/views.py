from django.views.generic import ListView

from .models import GalleryImage


class GalleryView(ListView):
    template_name = "gallery/gallery.html"
    context_object_name = "images"

    def get_queryset(self):
        return GalleryImage.objects.active()
