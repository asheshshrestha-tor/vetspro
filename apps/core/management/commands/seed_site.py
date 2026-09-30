"""Load the hospital's details and starter content. Safe to run more than once."""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import HeroSlide, SiteSettings, Stat
from apps.faq.models import FAQ, FAQCategory
from apps.pricing.models import PriceCategory, PriceItem
from apps.services.models import Service

DESCRIPTION = (
    "Open 24/7, we provide expert emergency and critical care for pets when every second counts. "
    "With advanced diagnostics, a skilled medical team, and compassionate support, "
    "we're here for you and your pet day or night."
)

SITE = {
    "name": "BMB Veterinary Hospital & 24 Hrs Emergency Service",
    "short_name": "BMB Vets",
    "tagline": "Expert emergency and critical care for pets, day or night.",
    "description": DESCRIPTION,
    "phone": "976-5960063",
    "whatsapp": "+977 976-5960063",
    "opening_hours": "Open 24 hours, 7 days a week",
    "instagram_url": "https://www.instagram.com/bmb_veterinary_hospital/",
    "tiktok_url": "https://www.tiktok.com/@bmbvets",
    "about_heading": "Our goal: Happy & Healthy Pets",
    "about_text": (
        "BMB Veterinary Hospital is open around the clock, providing expert emergency and critical care "
        "for pets when every second counts.\n\n"
        "With advanced diagnostics, a skilled medical team, and compassionate support, "
        "we're here for you and your pet day or night."
    ),
    "philosophy_text": (
        "Every pet is part of a family. We treat each patient with the care we would want for our own, "
        "and we keep owners informed at every step."
    ),
}

SLIDES = [
    {
        "title": "Welcome to BMB Vets",
        "subtitle": "Expert emergency and critical care for pets when every second counts.",
        "button_text": "Contact us",
        "button_url": "/contact/",
    },
    {
        "title": "24 Hrs Emergency Service",
        "subtitle": "Advanced diagnostics, a skilled medical team, and compassionate support.",
        "button_text": "Our services",
        "button_url": "/services/",
    },
    {
        "title": "Here for you, day or night",
        "subtitle": "Our doors are open 24 hours a day, 7 days a week.",
        "button_text": "About us",
        "button_url": "/about/",
    },
]

STATS = [
    {"label": "Hours a day", "value": 24, "suffix": ""},
    {"label": "Days a week", "value": 7, "suffix": ""},
    {"label": "Days a year", "value": 365, "suffix": ""},
]

SERVICES = [
    {
        "title": "24 Hrs Emergency Care",
        "slug": "emergency-care",
        "icon": "fa-truck-medical",
        "summary": "Urgent care for your pet at any hour of the day or night.",
        "description": (
            "Emergencies do not keep office hours. Our hospital is open 24/7 so that your pet can be seen "
            "straight away, whenever something goes wrong.\n\n"
            "If you can, call ahead so our team can prepare for your arrival."
        ),
    },
    {
        "title": "Critical Care",
        "slug": "critical-care",
        "icon": "fa-heart-pulse",
        "summary": "Close monitoring and support for seriously ill or injured pets.",
        "description": (
            "Pets that are seriously ill or injured need constant attention. "
            "Our medical team provides careful monitoring and support through every stage of recovery."
        ),
    },
    {
        "title": "Advanced Diagnostics",
        "slug": "advanced-diagnostics",
        "icon": "fa-microscope",
        "summary": "Finding out what is wrong quickly, so treatment can start sooner.",
        "description": (
            "A fast, accurate diagnosis is the first step to the right treatment. "
            "Our diagnostic services help the medical team understand your pet's condition without delay."
        ),
    },
    {
        "title": "Veterinary Consultation",
        "slug": "veterinary-consultation",
        "icon": "fa-stethoscope",
        "summary": "Health checks and advice from our veterinary team.",
        "description": (
            "Bring your pet in for an examination and talk through any concerns with our veterinarians."
        ),
    },
    {
        "title": "Vaccines",
        "slug": "vaccines",
        "icon": "fa-syringe",
        "summary": "Protecting your pet against preventable diseases.",
        "description": (
            "Vaccination is one of the simplest ways to keep your pet healthy. "
            "Ask our team which vaccines your pet needs and when."
        ),
    },
    {
        "title": "Small Pets Care",
        "slug": "small-pets-care",
        "icon": "fa-paw",
        "summary": "Gentle care for rabbits and other small companions.",
        "description": (
            "Small pets have their own needs. Our team offers gentle, attentive care for smaller companions."
        ),
    },
]

FAQS = {
    "Emergencies": [
        (
            "Are you really open 24 hours?",
            "Yes. The hospital is open 24 hours a day, 7 days a week.",
        ),
        (
            "What should I do if my pet has an emergency?",
            "Call us straight away on 976-5960063 and bring your pet to the hospital. "
            "Calling ahead lets our team prepare before you arrive.",
        ),
    ],
    "Visiting the hospital": [
        (
            "How can I contact you?",
            "You can call or WhatsApp us on +977 976-5960063, or send a message through the contact page.",
        ),
        (
            "What should I bring to my pet's visit?",
            "If you have them, bring your pet's vaccination card, any previous medical records, "
            "and any medicines your pet is currently taking.",
        ),
    ],
}

PRICES = {
    "Cats & Dogs": ["Consultation", "Emergency consultation", "Vaccines", "Diagnostics"],
    "Small Animals": ["Consultation", "Emergency consultation", "Diagnostics"],
}


class Command(BaseCommand):
    help = "Load the hospital's details and starter content."

    @transaction.atomic
    def handle(self, *args, **options):
        site = SiteSettings.load()
        for field, value in SITE.items():
            # Never overwrite something an editor has already filled in.
            if not getattr(site, field) or field in ("name", "short_name"):
                setattr(site, field, value)
        site.save()

        for order, slide in enumerate(SLIDES):
            HeroSlide.objects.get_or_create(title=slide["title"], defaults={**slide, "order": order})

        for order, stat in enumerate(STATS):
            Stat.objects.get_or_create(label=stat["label"], defaults={**stat, "order": order})

        for order, service in enumerate(SERVICES):
            Service.objects.get_or_create(slug=service["slug"], defaults={**service, "order": order})

        for cat_order, (category_name, faqs) in enumerate(FAQS.items()):
            category, _ = FAQCategory.objects.get_or_create(name=category_name, defaults={"order": cat_order})
            for order, (question, answer) in enumerate(faqs):
                FAQ.objects.get_or_create(
                    category=category, question=question, defaults={"answer": answer, "order": order}
                )

        for cat_order, (category_name, items) in enumerate(PRICES.items()):
            category, _ = PriceCategory.objects.get_or_create(name=category_name, defaults={"order": cat_order})
            for order, name in enumerate(items):
                PriceItem.objects.get_or_create(category=category, name=name, defaults={"order": order})

        self.stdout.write(self.style.SUCCESS("Site content loaded."))
