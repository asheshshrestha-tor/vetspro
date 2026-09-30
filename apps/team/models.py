from django.db import models
from django.urls import reverse

from apps.core.models import ActiveQuerySet, PublishableModel


class TeamMember(PublishableModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110, unique=True)
    role = models.CharField(max_length=100, help_text="e.g. Veterinarian, Veterinary Technician")
    qualification = models.CharField(max_length=150, blank=True, help_text="e.g. B.V.Sc. & A.H.")
    photo = models.ImageField(upload_to="team/", blank=True)
    short_bio = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)

    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)

    objects = ActiveQuerySet.as_manager()

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("team:detail", kwargs={"slug": self.slug})


class Experience(models.Model):
    member = models.ForeignKey(TeamMember, related_name="experiences", on_delete=models.CASCADE)
    title = models.CharField(max_length=150, blank=True)
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or self.description[:50]
