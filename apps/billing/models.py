from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Max, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.shop.models import StockMovement, change_stock

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


class Invoice(TimeStampedModel):
    """A bill for a counter sale or for a visit. Stock moves and the number is given when it is issued."""

    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [(DRAFT, "Draft"), (ISSUED, "Issued"), (PAID, "Paid"), (CANCELLED, "Cancelled")]
    STATUS_COLORS = {DRAFT: "secondary", ISSUED: "warning", PAID: "success", CANCELLED: "danger"}

    number = models.CharField("invoice no.", max_length=30, blank=True, editable=False)
    branch = models.ForeignKey("branches.Branch", related_name="invoices", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    invoice_date = models.DateField(default=timezone.localdate, db_index=True)

    client = models.ForeignKey(
        "clients.Client", related_name="invoices", on_delete=models.PROTECT, null=True, blank=True, verbose_name="customer"
    )
    customer_name = models.CharField(max_length=150, blank=True, help_text="For a customer without a client record.")
    customer_phone = models.CharField(max_length=30, blank=True)
    appointment = models.ForeignKey(
        "appointments.Appointment", related_name="invoices", on_delete=models.PROTECT, null=True, blank=True
    )

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    vat_percent = models.DecimalField("VAT %", max_digits=5, decimal_places=2, default=ZERO)
    vat_amount = models.DecimalField("VAT", max_digits=12, decimal_places=2, default=ZERO, editable=False)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    notes = models.TextField(blank=True, help_text="Printed on the invoice.")

    issued_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancel_reason = models.CharField(max_length=255, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["number"], condition=~Q(number=""), name="invoice_unique_number")
        ]
        permissions = [
            ("issue_invoice", "Can issue invoices"),
            ("record_payment", "Can record payments"),
            ("cancel_invoice", "Can cancel issued invoices"),
        ]

    def __str__(self):
        return self.display_number

    def get_absolute_url(self):
        return reverse("dashboard:edit", args=["billing", "invoice", self.pk])

    def save(self, *args, **kwargs):
        if self.branch_id is None:
            # Bills made outside the screens: the visit's branch, or the main branch.
            from apps.branches.models import Branch

            self.branch_id = self.appointment.branch_id if self.appointment_id else Branch.main().pk
        super().save(*args, **kwargs)

    @property
    def display_number(self):
        return self.number or f"Draft #{self.pk}"

    @property
    def customer_display(self):
        if self.client_id:
            return self.client.full_name
        return self.customer_name or "Walk-in customer"

    @property
    def phone_display(self):
        return self.client.phone if self.client_id else self.customer_phone

    @property
    def balance(self):
        return max(self.total - self.amount_paid, ZERO)

    @property
    def is_draft(self):
        return self.status == self.DRAFT

    @property
    def status_color(self):
        return self.STATUS_COLORS[self.status]

    @property
    def payment_label(self):
        if self.status in (self.DRAFT, self.CANCELLED):
            return self.get_status_display()
        if self.balance <= 0:
            return "Paid"
        return "Partly paid" if self.amount_paid > 0 else "Unpaid"

    # Totals

    def recalculate(self, save=True):
        self.subtotal = money(self.items.aggregate(total=Sum("line_total"))["total"])
        taxable = max(self.subtotal - money(self.discount), ZERO)
        self.vat_amount = money(taxable * money(self.vat_percent) / 100)
        self.total = taxable + self.vat_amount
        self.amount_paid = money(self.payments.aggregate(total=Sum("amount"))["total"])
        if self.status in (self.ISSUED, self.PAID):
            self.status = self.PAID if self.balance <= 0 else self.ISSUED
        if save:
            self.save(update_fields=["subtotal", "vat_amount", "total", "amount_paid", "status", "updated_at"])

    def clean(self):
        if self.discount and self.discount < 0:
            raise ValidationError({"discount": "The discount cannot be negative."})
        if self.appointment_id and self.client_id and self.appointment.client_id != self.client_id:
            raise ValidationError({"client": "The customer must be the owner on the appointment."})

    # Issuing and cancelling

    def _next_number(self):
        # Each branch numbers its own bills, e.g. INV-CBL-2026-00012.
        prefix = f"INV-{self.branch.code}-{self.invoice_date.year}-"
        last = Invoice.objects.filter(number__startswith=prefix).aggregate(last=Max("number"))["last"]
        return f"{prefix}{(int(last.rsplit('-', 1)[1]) + 1) if last else 1:05d}"

    def stock_lines(self):
        """(product, quantity) taken from stock by this bill; a package takes its contents."""
        lines = []
        for item in self.items.select_related("product"):
            product = item.product
            if product is None:
                continue
            if product.is_package:
                for part in product.package_items.select_related("component"):
                    if part.component.track_stock:
                        lines.append((part.component, part.quantity * item.quantity))
            elif product.track_stock:
                lines.append((product, item.quantity))
        return lines

    def issue(self, user):
        """Finalise the bill: take the items out of the branch's stock and give it the next number."""
        if not self.is_draft:
            raise ValidationError("Only a draft can be issued.")
        if not self.items.exists():
            raise ValidationError("Add at least one item before issuing the invoice.")
        with transaction.atomic():
            for product, quantity in self.stock_lines():
                change_stock(product, -quantity, StockMovement.SALE, user=user, invoice=self, branch=self.branch)
            self.invoice_date = timezone.localdate()
            self.issued_at = timezone.now()
            self.issued_by = user
            self.status = self.ISSUED
            self.recalculate(save=False)
            for attempt in range(5):
                self.number = self._next_number()
                try:
                    with transaction.atomic():
                        self.save()
                    break
                except IntegrityError:
                    if attempt == 4:
                        raise

    def cancel(self, user, reason=""):
        """Void an issued invoice and put its items back in stock. Drafts are deleted instead."""
        if self.status not in (self.ISSUED, self.PAID):
            raise ValidationError("Only an issued invoice can be cancelled.")
        with transaction.atomic():
            for product, quantity in self.stock_lines():
                change_stock(
                    product, quantity, StockMovement.SALE_CANCELLED, user=user, invoice=self, branch=self.branch
                )
            self.status = self.CANCELLED
            self.cancelled_at = timezone.now()
            self.cancel_reason = reason[:255]
            self.save()

    def add_payment(self, amount, method, user, reference=""):
        if self.status not in (self.ISSUED,):
            raise ValidationError("Payments can only be taken on an issued, unpaid invoice.")
        amount = money(amount)
        if amount <= 0:
            raise ValidationError("Enter an amount above zero.")
        if amount > self.balance:
            raise ValidationError(f"The amount due is only {self.balance}.")
        with transaction.atomic():
            payment = Payment.objects.create(invoice=self, amount=amount, method=method, reference=reference, received_by=user)
            self.recalculate()
        return payment


class InvoiceItem(models.Model):
    # Lines made by "Generate bill" are rebuilt from the visit each time; the rest are added by hand.
    MANUAL = ""
    FROM_TREATMENT = "treatment"
    VISIT_FEE = "visit_fee"
    SOURCES = [(MANUAL, "Added by hand"), (FROM_TREATMENT, "From treatment"), (VISIT_FEE, "Visit fee")]

    invoice = models.ForeignKey(Invoice, related_name="items", on_delete=models.CASCADE)
    source = models.CharField(max_length=10, choices=SOURCES, blank=True, default=MANUAL, editable=False)
    treatment = models.ForeignKey(
        "appointments.Treatment", related_name="invoice_items", on_delete=models.SET_NULL, null=True, blank=True,
        editable=False,
    )
    product = models.ForeignKey(
        "shop.Product", related_name="invoice_items", on_delete=models.PROTECT, null=True, blank=True
    )
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField("price", max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField("discount %", max_digits=5, decimal_places=2, default=ZERO)
    line_total = models.DecimalField("amount", max_digits=12, decimal_places=2, editable=False, default=ZERO)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.description

    @property
    def gross(self):
        return money(self.quantity * self.unit_price)

    @property
    def discount_amount(self):
        return self.gross - self.line_total

    def save(self, *args, **kwargs):
        discount = min(max(Decimal(self.discount_percent or 0), ZERO), Decimal(100))
        self.line_total = money(self.quantity * self.unit_price * (100 - discount) / 100)
        super().save(*args, **kwargs)


class Payment(models.Model):
    METHODS = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("esewa", "eSewa"),
        ("khalti", "Khalti"),
        ("fonepay", "Fonepay / QR"),
        ("bank", "Bank transfer"),
        ("other", "Other"),
    ]

    invoice = models.ForeignKey(Invoice, related_name="payments", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS, default="cash")
    reference = models.CharField(max_length=100, blank=True, help_text="Transaction ID for digital payments.")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["received_at", "id"]

    def __str__(self):
        return f"{self.amount} ({self.get_method_display()})"

    @property
    def receipt_number(self):
        return f"RCT-{self.pk:06d}"
