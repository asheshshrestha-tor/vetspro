import re

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublishableModel(TimeStampedModel):
    """Content that editors can order and hide from the public site."""

    order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")
    is_active = models.BooleanField("visible on site", default=True)

    class Meta:
        abstract = True
        ordering = ["order", "id"]


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


DEFAULT_CONSENT = (
    "I am the owner, or the person responsible, for the animal described above. I authorise the "
    "veterinarians and staff of this hospital to examine and treat my pet as they consider necessary, "
    "including the use of medicines, anaesthesia and procedures explained to me. I understand that "
    "every treatment carries some risk and that no result can be guaranteed. I agree to pay the charges "
    "for the services provided."
)


class SiteSettings(TimeStampedModel):
    """Single row holding the hospital's details shown across the site."""

    name = models.CharField(max_length=150, default="BMB Veterinary Hospital & 24 Hrs Emergency Service")
    short_name = models.CharField(max_length=60, default="BMB Vets")
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True, help_text="Short description used in the footer and search results.")

    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True, help_text="Include the country code, e.g. +977 ...")
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    map_embed_url = models.URLField(
        max_length=1000, blank=True, help_text="Google Maps embed URL (the src of the embed iframe)."
    )

    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    about_heading = models.CharField(max_length=150, blank=True)
    about_text = models.TextField(blank=True)
    about_image = models.ImageField(upload_to="site/", blank=True)
    philosophy_text = models.TextField(blank=True)
    philosophy_image = models.ImageField(upload_to="site/", blank=True)

    consent_text = models.TextField(
        "authorization text",
        blank=True,
        default=DEFAULT_CONSENT,
        help_text="Printed in the Authorization section of the visit form, above the owner's signature. "
        "Nepali text can be pasted here.",
    )

    pan_number = models.CharField("PAN / VAT no.", max_length=30, blank=True, help_text="Printed on invoices.")
    default_vat_percent = models.DecimalField(
        "default VAT %", max_digits=5, decimal_places=2, default=0,
        help_text="Applied to new invoices; 0 if the hospital does not charge VAT.",
    )
    visit_fee_item = models.ForeignKey(
        "shop.Product",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="fee added to every visit bill",
        help_text="e.g. the consultation fee. Leave blank to add fees by hand.",
    )
    invoice_footer = models.CharField(
        max_length=255, blank=True, default="Thank you for choosing us. Get well soon!",
        help_text="A short line printed at the bottom of every invoice.",
    )

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @staticmethod
    def _digits(value):
        return re.sub(r"\D", "", value or "")

    @property
    def phone_href(self):
        """Dialable number; falls back to the WhatsApp number, which carries the country code."""
        number = self.whatsapp if self.whatsapp else self.phone
        digits = self._digits(number)
        if not digits:
            return ""
        return f"tel:+{digits}" if number.strip().startswith("+") else f"tel:{digits}"

    @property
    def whatsapp_href(self):
        digits = self._digits(self.whatsapp)
        return f"https://wa.me/{digits}" if digits else ""


class HeroSlide(PublishableModel):
    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="hero/", blank=True)
    button_text = models.CharField(max_length=40, blank=True)
    button_url = models.CharField(max_length=200, blank=True, help_text="e.g. /contact/ or a full URL.")

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.title


class Stat(PublishableModel):
    label = models.CharField(max_length=60)
    value = models.PositiveIntegerField()
    suffix = models.CharField(max_length=10, blank=True, help_text="e.g. + or /7")

    objects = ActiveQuerySet.as_manager()

    class Meta(PublishableModel.Meta):
        verbose_name = "statistic"

    def __str__(self):
        return f"{self.label}: {self.value}{self.suffix}"
