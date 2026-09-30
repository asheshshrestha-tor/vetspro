from django.db import models

from apps.core.models import ActiveQuerySet, PublishableModel


class GalleryImage(PublishableModel):
    title = models.CharField(max_length=150, help_text="Also used as the image's alternative text.")
    image = models.ImageField(upload_to="gallery/")

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.title
