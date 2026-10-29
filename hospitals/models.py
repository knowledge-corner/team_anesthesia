import re

from django.conf import settings
from django.db import models
from django.urls import reverse

from core.models import TimeStampedModel


def normalise_name(text):
    """'Sahyadri Super-Speciality Hospital, Pune' -> 'sahyadri super speciality hospital pune'."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


class HospitalQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, merged_into__isnull=True)

    def search(self, query):
        """Every word must appear somewhere in the name, other names, area or city.

        Generic words (hospital, clinic, pvt ltd, ...) are ignored, so "Seatherney Hospital"
        also finds a hospital saved as just "Seatherney".
        """
        from .matching import meaningful_words

        qs = self
        for word in meaningful_words(query):
            qs = qs.filter(
                models.Q(name__icontains=word) | models.Q(aliases__icontains=word)
                | models.Q(area__icontains=word) | models.Q(city__icontains=word)
                | models.Q(pincode__startswith=word)
            )
        return qs


class Hospital(TimeStampedModel):
    """Shared hospital directory - one row per real hospital/clinic.

    Holds only facts about the place. Doctor-specific things (contacts,
    fees) live on Contact / ContactAffiliation / Case.
    """

    CATEGORY_CHOICES = [
        ("hospital", "Hospital"),
        ("nursing_home", "Nursing home"),
        ("clinic", "Clinic"),
        ("day_care", "Day-care / surgical centre"),
        ("other", "Other"),
    ]
    OWNERSHIP_CHOICES = [("", "Unknown"), ("government", "Government"), ("private", "Private"), ("trust", "Trust / charitable")]
    SOURCE_CHOICES = [
        ("directory", "Government directory (data.gov.in)"),
        ("starter", "Starter list"),
        ("doctor", "Added by a doctor"),
        ("admin", "Added by admin"),
    ]

    name = models.CharField(max_length=200, db_index=True)
    aliases = models.CharField("Other names", max_length=1000, blank=True,
                               help_text="Short or old names people search for, comma separated (e.g. KEM, Deenanath).")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="hospital")
    ownership = models.CharField(max_length=20, choices=OWNERSHIP_CHOICES, blank=True)
    area = models.CharField("Area / locality", max_length=120, blank=True)
    city = models.CharField(max_length=80, db_index=True)
    district = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    pincode = models.CharField("PIN code", max_length=10, blank=True)
    phone = models.CharField("Main phone", max_length=60, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="admin")
    legacy_ref = models.CharField("Source reference", max_length=100, blank=True, db_index=True)
    verified = models.BooleanField(default=False, help_text="Checked by an admin.")
    is_active = models.BooleanField(default=True)
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_from",
                                    help_text="Set when this entry was a duplicate of another hospital.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    objects = HospitalQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["city", "name"])]

    def __str__(self):
        return self.name

    @property
    def place(self):
        return ", ".join(p for p in (self.area, self.city) if p)

    @property
    def label(self):
        return f"{self.name} - {self.place}" if self.place else self.name

    def get_absolute_url(self):
        return reverse("hospitals:detail", args=[self.pk])


class HospitalMerge(models.Model):
    """Log of one merge (duplicate -> kept hospital) with everything that moved, so it can be undone."""

    kept = models.ForeignKey(Hospital, on_delete=models.PROTECT, related_name="merges_in")
    merged = models.ForeignKey(Hospital, on_delete=models.PROTECT, related_name="merges_out")
    merged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.merged} -> {self.kept}"
