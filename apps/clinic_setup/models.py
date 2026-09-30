from decimal import Decimal, InvalidOperation

from django.db import models
from django.utils.text import slugify

from apps.core.models import ActiveQuerySet, TimeStampedModel


class LookupModel(TimeStampedModel):
    """A list entry staff pick from. Retired entries are hidden, never deleted, so old records keep them."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first on the visit form.")
    is_active = models.BooleanField("in use", default=True, help_text="Untick to stop offering this for new visits.")

    objects = ActiveQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ValueDefinition(models.Model):
    """How the value of a visit field is entered and when it counts as abnormal.

    Admins define these fields; every visit then shows all of them, and staff
    only fill in the values.
    """

    NUMBER = "number"
    CHOICE = "choice"
    YES_NO = "yesno"
    TEXT = "text"
    VALUE_KINDS = [
        (NUMBER, "Number"),
        (CHOICE, "Choice from a list"),
        (YES_NO, "Yes / No"),
        (TEXT, "Free text"),
    ]
    YES_NO_OPTIONS = ["Yes", "No"]

    value_kind = models.CharField("value type", max_length=10, choices=VALUE_KINDS, default=TEXT)
    unit = models.CharField(max_length=30, blank=True, help_text="For numbers, e.g. °C or beats/min.")
    min_value = models.DecimalField("normal from", max_digits=8, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField("normal to", max_digits=8, decimal_places=2, null=True, blank=True)
    options = models.TextField(blank=True, help_text="For a choice: one option per line.")
    normal_options = models.TextField(
        "normal options",
        blank=True,
        help_text="For a choice or yes/no: the answers that count as normal, one per line. "
        "Anything else is flagged.",
    )

    class Meta:
        abstract = True

    @property
    def is_number(self):
        return self.value_kind == self.NUMBER

    @property
    def has_options(self):
        return self.value_kind in (self.CHOICE, self.YES_NO)

    @staticmethod
    def _lines(text):
        return [line.strip() for line in (text or "").splitlines() if line.strip()]

    @property
    def option_list(self):
        if self.value_kind == self.YES_NO:
            return list(self.YES_NO_OPTIONS)
        return self._lines(self.options)

    @property
    def normal_list(self):
        return self._lines(self.normal_options)

    @property
    def unit_suffix(self):
        return f" {self.unit}" if self.is_number and self.unit else ""

    @property
    def range_label(self):
        if self.is_number:
            low, high = self.min_value, self.max_value
            if low is not None and high is not None:
                return f"{low.normalize():f} – {high.normalize():f}{self.unit_suffix}"
            if low is not None:
                return f"≥ {low.normalize():f}{self.unit_suffix}"
            if high is not None:
                return f"≤ {high.normalize():f}{self.unit_suffix}"
            return ""
        if self.has_options:
            return ", ".join(self.normal_list)
        return ""

    def parse_number(self, value):
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None

    def is_abnormal(self, value):
        """True when a recorded value is outside the normal range. Blank and free-text values never are."""
        if value in (None, ""):
            return False
        if self.is_number:
            number = self.parse_number(value)
            if number is None:
                return False
            return (self.min_value is not None and number < self.min_value) or (
                self.max_value is not None and number > self.max_value
            )
        if self.has_options:
            normal = {option.lower() for option in self.normal_list}
            return bool(normal) and str(value).strip().lower() not in normal
        return False


class Species(LookupModel):
    class Meta(LookupModel.Meta):
        verbose_name_plural = "species"


class HistoryOption(ValueDefinition, LookupModel):
    """A point of the patient's history asked at every visit, e.g. vomiting or skin problems."""

    class Meta(LookupModel.Meta):
        verbose_name = "history field"
        verbose_name_plural = "history fields"


class VaccinationType(LookupModel):
    booster_interval_days = models.PositiveIntegerField(
        "booster interval (days)",
        null=True,
        blank=True,
        help_text="Used to suggest the next due date, e.g. 365 for a yearly booster.",
    )

    class Meta(LookupModel.Meta):
        verbose_name = "vaccination type"


class ExaminationType(ValueDefinition, TimeStampedModel):
    """A clinical examination recorded at every visit, e.g. temperature or CRT."""

    code = models.SlugField(max_length=60, unique=True, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first on the visit form.")
    is_active = models.BooleanField("in use", default=True, help_text="Untick to hide this from the visit form.")

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "examination field"
        verbose_name_plural = "examination fields"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            base = slugify(self.name)[:50] or "examination"
            code, number = base, 2
            while ExaminationType.objects.filter(code=code).exclude(pk=self.pk).exists():
                code, number = f"{base}-{number}", number + 1
            self.code = code
        super().save(*args, **kwargs)
