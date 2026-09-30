from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import SiteSettings

from .models import Invoice, InvoiceItem


def new_invoice(user, **fields):
    return Invoice.objects.create(vat_percent=SiteSettings.load().default_vat_percent, created_by=user, **fields)


def current_visit_bill(visit):
    return visit.invoices.exclude(status=Invoice.CANCELLED).order_by("-created_at").first()


def build_visit_bill(visit, user):
    """Create the visit's bill, or refresh its draft, from the treatments given.

    Lines that came from the visit (treatments and the visit fee) are rebuilt each time,
    so the bill always matches the Treatment tab; items added by hand, such as food from
    the shop, are kept. An issued bill is never changed.

    Returns (invoice, created).
    """
    invoice = current_visit_bill(visit)
    if invoice is not None and not invoice.is_draft:
        raise ValidationError(
            f"Bill {invoice.number} is already issued, so it was not changed. Cancel it first to bill the visit again."
        )

    with transaction.atomic():
        created = invoice is None
        if created:
            invoice = new_invoice(user, client=visit.client, appointment=visit)
        invoice.items.exclude(source=InvoiceItem.MANUAL).delete()

        fee = SiteSettings.load().visit_fee_item
        if fee is not None and fee.is_active:
            InvoiceItem.objects.create(
                invoice=invoice, product=fee, description=fee.name, quantity=1, unit_price=fee.price,
                source=InvoiceItem.VISIT_FEE,
            )

        for treatment in visit.treatments.select_related("item").order_by("id"):
            if not treatment.is_billable:
                continue
            InvoiceItem.objects.create(
                invoice=invoice,
                product=treatment.item,
                description=treatment.bill_description(),
                quantity=treatment.quantity,
                unit_price=treatment.unit_price,
                source=InvoiceItem.FROM_TREATMENT,
                treatment=treatment,
            )
        invoice.recalculate()
    return invoice, created
