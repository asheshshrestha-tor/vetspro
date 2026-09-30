from django.db import models
from django.urls import reverse

from apps.core.models import ActiveQuerySet, PublishableModel


class Service(PublishableModel):
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110, unique=True)
    icon = models.CharField(
        max_length=50, default="fa-paw", help_text="Font Awesome icon name, e.g. fa-paw, fa-syringe, fa-tooth."
    )
    summary = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="services/", blank=True)
    is_featured = models.BooleanField("show on home page", default=True)

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("services:detail", kwargs={"slug": self.slug})
