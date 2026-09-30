from django.db import models

from apps.core.models import ActiveQuerySet, PublishableModel


class FAQCategory(PublishableModel):
    name = models.CharField(max_length=100)

    objects = ActiveQuerySet.as_manager()

    class Meta(PublishableModel.Meta):
        verbose_name = "FAQ category"
        verbose_name_plural = "FAQ categories"

    def __str__(self):
        return self.name


class FAQ(PublishableModel):
    category = models.ForeignKey(FAQCategory, related_name="faqs", on_delete=models.CASCADE)
    service = models.ForeignKey(
        "services.Service",
        related_name="faqs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Also show this question on a service page.",
    )
    question = models.CharField(max_length=255)
    answer = models.TextField()

    objects = ActiveQuerySet.as_manager()

    class Meta(PublishableModel.Meta):
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question
