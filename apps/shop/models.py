from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
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

    def low_stock(self, branch_ids=None):
        """Products running low at any of the branches (all branches when none are given).

        A branch only counts once it has held the product, so a branch that never stocks
        an item is not warned about it.
        """
        stocks = BranchStock.objects.low(branch_ids)
        return self.filter(is_active=True, track_stock=True, pk__in=stocks.values("product_id"))

    def with_stock(self, branch_ids):
        """Annotate `branch_stock`: the stock held at these branches."""
        return self.annotate(
            branch_stock=Coalesce(
                Sum("branch_stocks__quantity", filter=Q(branch_stocks__branch_id__in=list(branch_ids))),
                Decimal("0"),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )


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
    # The total across all branches; each branch's own count is in BranchStock.
    stock_quantity = models.DecimalField(
        "in stock (all branches)", max_digits=10, decimal_places=2, default=0, editable=False
    )
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

    is_package = models.BooleanField(
        "package", default=False,
        help_text="A bundle sold at one price, e.g. a puppy vaccination package. Selling it takes its contents from stock.",
    )
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
    def shown_stock(self):
        """Stock at the branches being looked at, when annotated by with_stock(); otherwise the total."""
        return getattr(self, "branch_stock", self.stock_quantity)

    @property
    def is_low_stock(self):
        return self.track_stock and self.shown_stock <= self.low_stock_level

    @property
    def is_out_of_stock(self):
        return self.track_stock and self.shown_stock <= 0

    def stock_at(self, branch):
        if branch is None:
            return self.stock_quantity
        row = BranchStock.objects.filter(product=self, branch=branch).values_list("quantity", flat=True).first()
        return Decimal("0") if row is None else row

    def price_at(self, branch):
        """The branch's own price if it has one; otherwise the hospital price."""
        if branch is None:
            return self.price
        override = BranchPrice.objects.filter(product=self, branch=branch).values_list("price", flat=True).first()
        return self.price if override is None else override

    @property
    def is_online(self):
        return self.is_active and self.show_online and self.category.is_active and self.category.show_online


class PackageItem(models.Model):
    """One thing inside a package, and how many of it."""

    package = models.ForeignKey(Product, related_name="package_items", on_delete=models.CASCADE)
    component = models.ForeignKey(Product, related_name="in_packages", on_delete=models.PROTECT, verbose_name="item")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    class Meta:
        ordering = ["id"]
        verbose_name = "package item"

    def __str__(self):
        return f"{self.component} × {self.quantity.normalize():f}"

    def clean(self):
        if self.component_id and self.component_id == self.package_id:
            raise ValidationError({"component": "A package cannot contain itself."})
        if self.component_id and self.component.is_package:
            raise ValidationError({"component": "A package cannot contain another package."})


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
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    TRANSFER_BACK = "transfer_back"
    REASONS = [
        (OPENING, "Opening stock"),
        (PURCHASE, "Stock received"),
        (SALE, "Sold"),
        (SALE_CANCELLED, "Sale cancelled"),
        (RETURN, "Returned by customer"),
        (ADJUSTMENT, "Stock count correction"),
        (DAMAGED, "Damaged or expired"),
        (TRANSFER_OUT, "Sent to another branch"),
        (TRANSFER_IN, "Received from another branch"),
        (TRANSFER_BACK, "Transfer cancelled"),
    ]
    # Reasons staff choose by hand; sales are recorded by invoices.
    MANUAL_REASONS = [
        (PURCHASE, "Stock received"),
        (RETURN, "Returned by customer"),
        (ADJUSTMENT, "Stock count correction"),
        (DAMAGED, "Damaged or expired"),
    ]

    product = models.ForeignKey(Product, related_name="stock_movements", on_delete=models.PROTECT)
    branch = models.ForeignKey("branches.Branch", related_name="stock_movements", on_delete=models.PROTECT)
    quantity = models.DecimalField("change", max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REASONS)
    note = models.CharField(max_length=255, blank=True)
    invoice = models.ForeignKey(
        "billing.Invoice", related_name="stock_movements", on_delete=models.SET_NULL, null=True, blank=True
    )
    transfer = models.ForeignKey(
        "StockTransfer", related_name="stock_movements", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "stock movement"

    def __str__(self):
        return f"{self.product}: {self.quantity:+}"


class BranchStockQuerySet(models.QuerySet):
    def low(self, branch_ids=None):
        rows = self.filter(product__is_active=True, product__track_stock=True).filter(
            quantity__lte=Coalesce(F("low_stock_level"), F("product__low_stock_level"))
        )
        if branch_ids is not None:
            rows = rows.filter(branch_id__in=list(branch_ids))
        return rows


class BranchStock(models.Model):
    """How much of a product one branch holds."""

    product = models.ForeignKey(Product, related_name="branch_stocks", on_delete=models.CASCADE)
    branch = models.ForeignKey("branches.Branch", related_name="stocks", on_delete=models.CASCADE)
    quantity = models.DecimalField("in stock", max_digits=10, decimal_places=2, default=0)
    low_stock_level = models.DecimalField(
        "low-stock warning at", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Leave blank to use the product's level.",
    )

    objects = BranchStockQuerySet.as_manager()

    class Meta:
        ordering = ["branch__order", "branch__name"]
        constraints = [models.UniqueConstraint(fields=["product", "branch"], name="branchstock_unique_product_branch")]
        verbose_name = "branch stock"

    def __str__(self):
        return f"{self.product} at {self.branch}"

    @property
    def warning_level(self):
        return self.product.low_stock_level if self.low_stock_level is None else self.low_stock_level

    @property
    def is_low(self):
        return self.quantity <= self.warning_level


class BranchPrice(models.Model):
    """A branch's own selling price for a product. Without one, the branch sells at the hospital price."""

    product = models.ForeignKey(Product, related_name="branch_prices", on_delete=models.CASCADE)
    branch = models.ForeignKey("branches.Branch", related_name="prices", on_delete=models.CASCADE)
    price = models.DecimalField("branch price", max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "branch__order", "branch__name"]
        constraints = [models.UniqueConstraint(fields=["product", "branch"], name="branchprice_unique_product_branch")]
        verbose_name = "branch price"

    def __str__(self):
        return f"{self.product} at {self.branch}: {self.price}"

    @property
    def differs(self):
        return self.price != self.product.price


def change_stock(product, quantity, reason, user=None, note="", invoice=None, branch=None, transfer=None):
    """Add (positive) or remove (negative) stock at a branch and log it. Refuses to go below zero.

    Without a branch the main branch is used, e.g. for sample data and imports.
    """
    from apps.branches.models import Branch

    quantity = Decimal(quantity)
    branch = branch or Branch.main()
    with transaction.atomic():
        row, _ = BranchStock.objects.get_or_create(product=product, branch=branch)
        updated = BranchStock.objects.filter(pk=row.pk).filter(
            Q(quantity__gte=-quantity) if quantity < 0 else Q()
        ).update(quantity=F("quantity") + quantity)
        if not updated:
            row.refresh_from_db(fields=["quantity"])
            raise ValidationError(
                f"Only {row.quantity.normalize():f} {product.unit} of “{product.name}” in stock at {branch}."
            )
        Product.objects.filter(pk=product.pk).update(stock_quantity=F("stock_quantity") + quantity)
        product.refresh_from_db(fields=["stock_quantity"])
        row.refresh_from_db(fields=["quantity"])
        return StockMovement.objects.create(
            product=product,
            branch=branch,
            quantity=quantity,
            balance_after=row.quantity,
            reason=reason,
            note=note,
            invoice=invoice,
            transfer=transfer,
            created_by=user,
        )


class StockTransfer(TimeStampedModel):
    """Stock sent from one branch to another. It leaves when sent and arrives when received."""

    DRAFT = "draft"
    SENT = "sent"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [(DRAFT, "Draft"), (SENT, "On the way"), (RECEIVED, "Received"), (CANCELLED, "Cancelled")]
    STATUS_COLORS = {DRAFT: "secondary", SENT: "warning", RECEIVED: "success", CANCELLED: "danger"}

    number = models.CharField("transfer no.", max_length=20, unique=True, editable=False)
    from_branch = models.ForeignKey(
        "branches.Branch", related_name="transfers_out", on_delete=models.PROTECT, verbose_name="from"
    )
    to_branch = models.ForeignKey(
        "branches.Branch", related_name="transfers_in", on_delete=models.PROTECT, verbose_name="to"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True, editable=False)
    note = models.CharField(max_length=255, blank=True, help_text="e.g. who is carrying it.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    received_at = models.DateTimeField(null=True, blank=True, editable=False)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "stock transfer"
        permissions = [("receive_stocktransfer", "Can receive stock transfers")]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("dashboard:edit", args=["shop", "stocktransfer", self.pk])

    @property
    def status_color(self):
        return self.STATUS_COLORS[self.status]

    def save(self, *args, **kwargs):
        if not self.number:
            last = StockTransfer.objects.order_by("-id").values_list("number", flat=True).first()
            number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
            while StockTransfer.objects.filter(number=f"TRF-{number:05d}").exists():
                number += 1
            self.number = f"TRF-{number:05d}"
        super().save(*args, **kwargs)

    def clean(self):
        if self.from_branch_id and self.from_branch_id == self.to_branch_id:
            raise ValidationError({"to_branch": "Choose a different branch to send to."})

    def _move(self, sign, reason, branch, user):
        for item in self.items.select_related("product"):
            change_stock(
                item.product, sign * item.quantity, reason, user=user, branch=branch, transfer=self, note=self.note
            )

    def send(self, user):
        """Take the items out of the sending branch's stock."""
        if self.status != self.DRAFT:
            raise ValidationError("Only a draft transfer can be sent.")
        if not self.items.exists():
            raise ValidationError("Add at least one item before sending.")
        with transaction.atomic():
            self._move(-1, StockMovement.TRANSFER_OUT, self.from_branch, user)
            self.status, self.sent_at, self.sent_by = self.SENT, timezone.now(), user
            self.save()

    def receive(self, user):
        """Add the items to the receiving branch's stock."""
        if self.status != self.SENT:
            raise ValidationError("Only a transfer on the way can be received.")
        with transaction.atomic():
            self._move(1, StockMovement.TRANSFER_IN, self.to_branch, user)
            self.status, self.received_at, self.received_by = self.RECEIVED, timezone.now(), user
            self.save()

    def cancel(self, user):
        """Stop a transfer; stock already sent goes back to the sending branch."""
        if self.status not in (self.DRAFT, self.SENT):
            raise ValidationError("A received transfer cannot be cancelled.")
        with transaction.atomic():
            if self.status == self.SENT:
                self._move(1, StockMovement.TRANSFER_BACK, self.from_branch, user)
            self.status = self.CANCELLED
            self.save()


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(StockTransfer, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="+", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product} × {self.quantity.normalize():f}"
