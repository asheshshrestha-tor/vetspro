"""Attach the images in seed_media/ to the matching content. Safe to run more than once."""
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from apps.core.models import HeroSlide, SiteSettings
from apps.gallery.models import GalleryImage
from apps.pricing.models import PriceCategory
from apps.services.models import Service

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = "Attach the images in seed_media/ to the matching content."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(settings.BASE_DIR / "seed_media"), help="Folder to read from.")
        parser.add_argument("--replace", action="store_true", help="Replace images that are already set.")

    def handle(self, *args, **options):
        self.folder = Path(options["path"])
        self.replace = options["replace"]
        self.attached = 0

        if not self.folder.is_dir():
            self.stderr.write(f"Folder not found: {self.folder}")
            return

        site = SiteSettings.load()
        self.attach(site, "about_image", "about")
        self.attach(site, "philosophy_image", "philosophy")

        for number, slide in enumerate(HeroSlide.objects.order_by("order", "id"), start=1):
            self.attach(slide, "image", f"hero-{number}")

        for service in Service.objects.all():
            self.attach(service, "image", f"service-{service.slug}")

        for number, category in enumerate(PriceCategory.objects.order_by("order", "id"), start=1):
            self.attach(category, "image", f"pricing-{number}")

        self.load_gallery()

        self.stdout.write(self.style.SUCCESS(f"{self.attached} image(s) attached."))

    def find(self, stem):
        for path in sorted(self.folder.iterdir()):
            if path.is_file() and path.stem.lower() == stem and path.suffix.lower() in EXTENSIONS:
                return path
        return None

    def attach(self, obj, field_name, stem):
        path = self.find(stem)
        if path is None:
            self.stdout.write(f"  missing  {stem}")
            return
        field = getattr(obj, field_name)
        if field and not self.replace:
            self.stdout.write(f"  kept     {stem} (already set, use --replace to overwrite)")
            return
        with path.open("rb") as handle:
            field.save(path.name, File(handle), save=True)
        self.attached += 1
        self.stdout.write(f"  attached {path.name}")

    def load_gallery(self):
        folder = self.folder / "gallery"
        if not folder.is_dir():
            return
        for order, path in enumerate(sorted(folder.iterdir())):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            title = path.stem.replace("-", " ").replace("_", " ").strip().capitalize()
            if GalleryImage.objects.filter(title=title).exists():
                self.stdout.write(f"  kept     gallery/{path.name} (already added)")
                continue
            image = GalleryImage(title=title, order=order)
            with path.open("rb") as handle:
                image.image.save(path.name, File(handle), save=True)
            self.attached += 1
            self.stdout.write(f"  attached gallery/{path.name}")
