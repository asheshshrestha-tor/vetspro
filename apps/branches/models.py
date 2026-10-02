import re

from django.db import models

from apps.core.models import ActiveQuerySet, TimeStampedModel


class Branch(TimeStampedModel):
    """A place where the hospital works. Visits, bills and stock belong to a branch;
    owners, pets, the catalogue and staff accounts are shared by all branches."""

    name = models.CharField(max_length=100, unique=True, help_text="e.g. Chabahil")
    code = models.CharField(
        max_length=10, unique=True, help_text="Short code used in invoice numbers, e.g. CBL. Letters and digits only."
    )
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True, help_text="Include the country code, e.g. +977 ...")
    email = models.EmailField(blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    map_embed_url = models.URLField("map embed URL", max_length=1000, blank=True)

    # Blank means "use the hospital-wide value from Site settings".
    pan_number = models.CharField("PAN / VAT no.", max_length=30, blank=True, help_text="Leave blank to use the hospital's.")
    vat_percent = models.DecimalField(
        "VAT %", max_digits=5, decimal_places=2, null=True, blank=True, help_text="Leave blank to use the hospital's."
    )
    visit_fee_item = models.ForeignKey(
        "shop.Product", related_name="+", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="fee added to every visit bill", help_text="Leave blank to use the hospital's.",
    )
    invoice_footer = models.CharField(max_length=255, blank=True, help_text="Leave blank to use the hospital's.")

    is_main = models.BooleanField("main branch", default=False)
    is_active = models.BooleanField("open", default=True, help_text="Untick when a branch closes. Its history is kept.")
    order = models.PositiveIntegerField(default=0)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["-is_main", "order", "name"]
        verbose_name_plural = "branches"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.code = re.sub(r"[^A-Za-z0-9]", "", self.code or "").upper()[:10]
        super().save(*args, **kwargs)
        if self.is_main:
            Branch.objects.exclude(pk=self.pk).filter(is_main=True).update(is_main=False)

    @classmethod
    def main(cls):
        return cls.objects.filter(is_active=True).order_by("-is_main", "order", "id").first()

    # Values that fall back to the hospital's Site settings.

    def _site(self):
        from apps.core.models import SiteSettings

        return SiteSettings.load()

    @property
    def effective_pan(self):
        return self.pan_number or self._site().pan_number

    @property
    def effective_vat_percent(self):
        return self.vat_percent if self.vat_percent is not None else self._site().default_vat_percent

    @property
    def effective_visit_fee_item(self):
        return self.visit_fee_item or self._site().visit_fee_item

    @property
    def effective_invoice_footer(self):
        return self.invoice_footer or self._site().invoice_footer

    @property
    def effective_phone(self):
        return self.phone or self._site().phone

    @property
    def effective_address(self):
        return self.address or self._site().address

    @staticmethod
    def _digits(value):
        return re.sub(r"\D", "", value or "")

    @property
    def phone_href(self):
        number = self.whatsapp or self.phone
        digits = self._digits(number)
        if not digits:
            return ""
        return f"tel:+{digits}" if number.strip().startswith("+") else f"tel:{digits}"

    @property
    def whatsapp_href(self):
        digits = self._digits(self.whatsapp)
        return f"https://wa.me/{digits}" if digits else ""
