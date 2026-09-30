from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ActiveQuerySet, PublishableModel


class Testimonial(PublishableModel):
    name = models.CharField(max_length=100)
    detail = models.CharField(max_length=100, blank=True, help_text="e.g. the pet's name or the owner's town.")
    quote = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    photo = models.ImageField(upload_to="testimonials/", blank=True)

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.name

    @property
    def stars(self):
        return range(self.rating)
