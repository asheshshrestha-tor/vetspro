from django.db import models

from apps.core.models import ActiveQuerySet, PublishableModel


class PriceCategory(PublishableModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="pricing/", blank=True)

    objects = ActiveQuerySet.as_manager()

    class Meta(PublishableModel.Meta):
        verbose_name_plural = "price categories"

    def __str__(self):
        return self.name


class PriceItem(PublishableModel):
    category = models.ForeignKey(PriceCategory, related_name="items", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Leave empty to show 'On request'."
    )
    is_starting_price = models.BooleanField("show as 'from'", default=False)

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.name
