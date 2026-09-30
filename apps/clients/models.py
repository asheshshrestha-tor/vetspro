import datetime
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ActiveQuerySet, TimeStampedModel

COUNTRY_CODE = "977"


def normalize_phone(value):
    """Digits only, without Nepal's country code, so "+977 976-5960063" matches "9765960063"."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith(COUNTRY_CODE) and len(digits) > 10:
        digits = digits[len(COUNTRY_CODE):]
    return digits


class Client(TimeStampedModel):
    """A pet owner. One client can bring several pets and come back many times."""

    full_name = models.CharField("owner's name", max_length=150)
    phone = models.CharField("phone", max_length=30)
    phone_digits = models.CharField(max_length=30, editable=False, db_index=True)
    alt_phone = models.CharField("alternate phone", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    area = models.CharField("area / city", max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField("active", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False, related_name="+"
    )

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["full_name", "id"]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"

    def save(self, *args, **kwargs):
        self.phone_digits = normalize_phone(self.phone)
        if kwargs.get("update_fields") is not None and "phone" in kwargs["update_fields"]:
            kwargs["update_fields"] = {*kwargs["update_fields"], "phone_digits"}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("dashboard:client_record", args=[self.pk])

    def same_phone(self):
        """Other clients with this phone number. Families share phones, so this is a warning only."""
        digits = normalize_phone(self.phone)
        if not digits:
            return Client.objects.none()
        return Client.objects.filter(phone_digits=digits).exclude(pk=self.pk)


class Pet(TimeStampedModel):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"
    SEX_CHOICES = [(MALE, "Male"), (FEMALE, "Female"), (UNKNOWN, "Unknown")]

    client = models.ForeignKey(Client, related_name="pets", on_delete=models.CASCADE, verbose_name="owner")
    name = models.CharField(max_length=100)
    species = models.ForeignKey("clinic_setup.Species", related_name="pets", on_delete=models.PROTECT)
    breed = models.CharField(max_length=100, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, default=UNKNOWN)
    is_neutered = models.BooleanField("neutered / spayed", default=False)
    date_of_birth = models.DateField(null=True, blank=True)
    dob_is_estimate = models.BooleanField("date of birth is approximate", default=False)
    color = models.CharField("colour and markings", max_length=100, blank=True)
    microchip_number = models.CharField(max_length=50, blank=True)
    alerts = models.TextField(
        "allergies and alerts", blank=True, help_text="Shown as a warning on every visit, e.g. “Allergic to penicillin”."
    )
    photo = models.ImageField(upload_to="pets/", blank=True)
    is_deceased = models.BooleanField("deceased", default=False)
    date_of_death = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField("active", default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return f"{self.name} ({self.species})" if self.species_id else self.name

    def get_absolute_url(self):
        return reverse("dashboard:pet_record", args=[self.pk])

    def clean(self):
        today = timezone.localdate()
        if self.date_of_birth and self.date_of_birth > today:
            raise ValidationError({"date_of_birth": "The date of birth cannot be in the future."})
        if self.date_of_death and not self.is_deceased:
            raise ValidationError({"date_of_death": "Tick “deceased” to record a date of death."})
        if self.date_of_death and self.date_of_birth and self.date_of_death < self.date_of_birth:
            raise ValidationError({"date_of_death": "The date of death cannot be before the date of birth."})

    @property
    def age(self):
        """(years, months), counted to today or to the date of death."""
        if not self.date_of_birth:
            return None
        end = self.date_of_death or timezone.localdate()
        months = (end.year - self.date_of_birth.year) * 12 + end.month - self.date_of_birth.month
        if end.day < self.date_of_birth.day:
            months -= 1
        months = max(months, 0)
        return divmod(months, 12)

    @property
    def age_display(self):
        age = self.age
        if age is None:
            return ""
        years, months = age
        if years and months:
            text = f"{years} y {months} m"
        elif years:
            text = f"{years} y"
        else:
            text = f"{months} m"
        return f"~{text}" if self.dob_is_estimate else text

    @staticmethod
    def estimate_birth_date(years, months, today=None):
        today = today or timezone.localdate()
        total = (years or 0) * 12 + (months or 0)
        year, month = divmod(today.year * 12 + today.month - 1 - total, 12)
        day = min(today.day, 28)
        return datetime.date(year, month + 1, day)
