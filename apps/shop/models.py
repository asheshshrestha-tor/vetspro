from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils.text import slugify

from apps.core.models import ActiveQuerySet, TimeStampedModel


def unique_slug(instance, value, max_length=110):
    base = slugify(value)[: max_length - 6] or "item"
    slug, number = base, 2
    model = type(instance)
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug, number = f"{base}-{number}", number + 1
    return slug


class ProductCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=110, unique=True, editable=False)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="shop/categories/", blank=True)
    show_online = models.BooleanField(
        "show in the online shop", default=True, help_text="Untick for things only sold at the counter, e.g. clinic services."
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField("in use", default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "product category"
        verbose_name_plural = "product categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("shop:category", kwargs={"slug": self.slug})


class ProductQuerySet(ActiveQuerySet):
    def online(self):
        return self.filter(is_active=True, show_online=True, category__is_active=True, category__show_online=True)

    def low_stock(self):
        return self.filter(is_active=True, track_stock=True, stock_quantity__lte=F("low_stock_level"))


class Product(TimeStampedModel):
    """Anything the hospital sells: medicines, food, toys, cages, and clinic services."""

    category = models.ForeignKey(ProductCategory, related_name="products", on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, editable=False)
    sku = models.CharField("SKU / code", max_length=50, blank=True, help_text="Your own product code or barcode.")
    brand = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30, default="piece", help_text="How it is sold, e.g. piece, tablet, bottle, kg.")
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="shop/products/", blank=True)

    price = models.DecimalField("selling price", max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(
        "cost price", max_digits=10, decimal_places=2, null=True, blank=True, help_text="Only shown to staff."
    )

    track_stock = models.BooleanField(
        default=True, help_text="Untick for services and anything you do not count, such as a consultation fee."
    )
    stock_quantity = models.DecimalField("in stock", max_digits=10, decimal_places=2, default=0, editable=False)
    low_stock_level = models.DecimalField(
        "low-stock warning at", max_digits=10, decimal_places=2, default=5, help_text="Warn when stock falls to this."
    )

    # Items vets can pick in a visit's Treatment tab, with what they usually prescribe.
    MEDICINE = "medicine"
    PROCEDURE = "procedure"
    ADVICE = "advice"
    TREATMENT_KINDS = [(MEDICINE, "Medicine"), (PROCEDURE, "Procedure"), (ADVICE, "Advice")]
    treatment_kind = models.CharField(
        "treatment type", max_length=10, choices=TREATMENT_KINDS, blank=True,
        help_text="Makes this item available in the Treatment tab of a visit. Leave blank for shop-only items.",
    )
    default_dose = models.CharField(max_length=60, blank=True, help_text="e.g. 10 mg/kg")
    default_route = models.CharField(max_length=60, blank=True, help_text="e.g. oral, SC, IM, IV")
    default_frequency = models.CharField(max_length=60, blank=True, help_text="e.g. twice a day")
    default_duration = models.CharField(max_length=60, blank=True, help_text="e.g. 5 days")

    is_prescription = models.BooleanField(
        "prescription only", default=False, help_text="Sold only after a vet's advice; shown as such online."
    )
    show_online = models.BooleanField("show in the online shop", default=True)
    is_active = models.BooleanField("in use", default=True, help_text="Untick to stop selling it. Past invoices keep it.")

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        permissions = [("adjust_stock", "Can adjust stock")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name, max_length=160)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("shop:product", kwargs={"slug": self.slug})

    @property
    def is_low_stock(self):
        return self.track_stock and self.stock_quantity <= self.low_stock_level

    @property
    def is_out_of_stock(self):
        return self.track_stock and self.stock_quantity <= 0

    @property
    def is_online(self):
        return self.is_active and self.show_online and self.category.is_active and self.category.show_online


class TreatmentItemManager(models.Manager.from_queryset(ProductQuerySet)):
    def get_queryset(self):
        return super().get_queryset().exclude(treatment_kind="")


class TreatmentItem(Product):
    """The treatment catalogue: medicines, procedures and advice vets choose from in a visit.

    These are the same records as shop products, so a medicine has one price and one stock count
    whether it is sold at the counter or given in a treatment.
    """

    objects = TreatmentItemManager()

    class Meta:
        proxy = True
        ordering = ["treatment_kind", "name"]
        verbose_name = "treatment item"
        verbose_name_plural = "treatment catalogue"


class StockMovement(models.Model):
    """Every change to a product's stock, so the count can always be explained."""

    OPENING = "opening"
    PURCHASE = "purchase"
    SALE = "sale"
    SALE_CANCELLED = "sale_cancelled"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    DAMAGED = "damaged"
    REASONS = [
        (OPENING, "Opening stock"),
        (PURCHASE, "Stock received"),
        (SALE, "Sold"),
        (SALE_CANCELLED, "Sale cancelled"),
        (RETURN, "Returned by customer"),
        (ADJUSTMENT, "Stock count correction"),
        (DAMAGED, "Damaged or expired"),
    ]
    # Reasons staff choose by hand; sales are recorded by invoices.
    MANUAL_REASONS = [
        (PURCHASE, "Stock received"),
        (RETURN, "Returned by customer"),
        (ADJUSTMENT, "Stock count correction"),
        (DAMAGED, "Damaged or expired"),
    ]

    product = models.ForeignKey(Product, related_name="stock_movements", on_delete=models.PROTECT)
    quantity = models.DecimalField("change", max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REASONS)
    note = models.CharField(max_length=255, blank=True)
    invoice = models.ForeignKey(
        "billing.Invoice", related_name="stock_movements", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "stock movement"

    def __str__(self):
        return f"{self.product}: {self.quantity:+}"


def change_stock(product, quantity, reason, user=None, note="", invoice=None):
    """Add (positive) or remove (negative) stock and log it. Refuses to go below zero."""
    quantity = Decimal(quantity)
    with transaction.atomic():
        updated = Product.objects.filter(pk=product.pk).filter(
            Q(stock_quantity__gte=-quantity) if quantity < 0 else Q()
        ).update(stock_quantity=F("stock_quantity") + quantity)
        if not updated:
            product.refresh_from_db(fields=["stock_quantity"])
            raise ValidationError(
                f"Only {product.stock_quantity.normalize():f} {product.unit} of “{product.name}” in stock."
            )
        product.refresh_from_db(fields=["stock_quantity"])
        return StockMovement.objects.create(
            product=product,
            quantity=quantity,
            balance_after=product.stock_quantity,
            reason=reason,
            note=note,
            invoice=invoice,
            created_by=user,
        )
