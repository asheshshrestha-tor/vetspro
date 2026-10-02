"""The figures on the Reports page. Every function takes a date range and the branches to include."""
import datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.appointments.models import Appointment
from apps.billing.models import Invoice, InvoiceItem, Payment
from apps.clients.models import Client
from apps.shop.models import BranchStock

ZERO = Decimal("0")
METHOD_LABELS = dict(Payment.METHODS)
MONEY = DecimalField(max_digits=14, decimal_places=2)


def total(queryset, field):
    return queryset.aggregate(value=Coalesce(Sum(field), Value(ZERO), output_field=MONEY))["value"]


def days_between(start, end):
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def sales(start, end, branch_ids):
    issued = Invoice.objects.filter(
        branch_id__in=branch_ids, status__in=[Invoice.ISSUED, Invoice.PAID], invoice_date__range=(start, end)
    )
    payments = Payment.objects.filter(
        invoice__branch_id__in=branch_ids, invoice__status__in=[Invoice.ISSUED, Invoice.PAID],
        received_at__date__range=(start, end),
    )
    by_day = dict(issued.values_list("invoice_date").annotate(value=Sum("total")))
    line_discounts = total(
        InvoiceItem.objects.filter(invoice__in=issued), F("quantity") * F("unit_price") - F("line_total")
    )
    outstanding = Invoice.objects.filter(branch_id__in=branch_ids, status=Invoice.ISSUED)
    return {
        "total": total(issued, "total"),
        "count": issued.count(),
        "vat": total(issued, "vat_amount"),
        "discounts": total(issued, "discount") + line_discounts,
        "received": total(payments, "amount"),
        "by_method": [
            {**row, "label": METHOD_LABELS.get(row["method"], row["method"])}
            for row in payments.values("method").annotate(value=Sum("amount"), count=Count("id")).order_by("-value")
        ],
        "outstanding": total(outstanding, "total") - total(outstanding, "amount_paid"),
        "outstanding_count": outstanding.count(),
        "daily": [{"date": day, "value": by_day.get(day, ZERO)} for day in days_between(start, end)],
        "by_branch": list(
            issued.values("branch__name").annotate(value=Sum("total"), count=Count("id")).order_by("-value")
        ),
    }


def visits(start, end, branch_ids):
    rows = Appointment.objects.filter(branch_id__in=branch_ids, visit_date__range=(start, end))
    by_day = dict(
        rows.exclude(status=Appointment.CANCELLED).values_list("visit_date").annotate(value=Count("id"))
    )
    labels = dict(Appointment.STATUS_CHOICES)
    return {
        "count": rows.exclude(status=Appointment.CANCELLED).count(),
        "completed": rows.filter(status=Appointment.COMPLETED).count(),
        "cancelled": rows.filter(status=Appointment.CANCELLED).count(),
        "emergencies": rows.filter(priority=Appointment.EMERGENCY).count(),
        "by_status": [
            {"label": labels[row["status"]], "count": row["count"]}
            for row in rows.values("status").annotate(count=Count("id")).order_by("-count")
        ],
        "by_species": list(
            rows.exclude(status=Appointment.CANCELLED).values("pet__species__name")
            .annotate(count=Count("id")).order_by("-count")[:8]
        ),
        "new_clients": Client.objects.filter(created_at__date__range=(start, end)).count(),
        "daily": [{"date": day, "value": by_day.get(day, 0)} for day in days_between(start, end)],
    }


def providers(start, end, branch_ids):
    """Visits and billed amounts by the vet who attended."""
    visits = (
        Appointment.objects.filter(branch_id__in=branch_ids, visit_date__range=(start, end))
        .exclude(status=Appointment.CANCELLED)
        .values("attended_by", "attended_by__first_name", "attended_by__last_name", "attended_by__username")
        .annotate(
            visits=Count("id", distinct=True),
            completed=Count("id", filter=Q(status=Appointment.COMPLETED), distinct=True),
        )
    )
    billed = dict(
        Invoice.objects.filter(
            branch_id__in=branch_ids, status__in=[Invoice.ISSUED, Invoice.PAID], invoice_date__range=(start, end),
            appointment__isnull=False,
        ).values_list("appointment__attended_by").annotate(value=Sum("total"))
    )
    rows = []
    for row in visits:
        name = " ".join(filter(None, [row["attended_by__first_name"], row["attended_by__last_name"]])) or row["attended_by__username"]
        rows.append({
            "name": name or "Not assigned",
            "visits": row["visits"],
            "completed": row["completed"],
            "billed": billed.get(row["attended_by"], ZERO),
        })
    return sorted(rows, key=lambda row: (-row["visits"], row["name"]))


def top_items(start, end, branch_ids, limit=15):
    """What sold most, by revenue: services, medicines and shop products."""
    items = InvoiceItem.objects.filter(
        invoice__branch_id__in=branch_ids, invoice__status__in=[Invoice.ISSUED, Invoice.PAID],
        invoice__invoice_date__range=(start, end),
    )
    # Catalogue items are counted together whatever their line said; hand-written lines by their text.
    products = (
        items.filter(product__isnull=False)
        .values("product_id", "product__name", "product__category__name")
        .annotate(quantity=Sum("quantity"), revenue=Sum("line_total"), lines=Count("id"))
    )
    manual = (
        items.filter(product__isnull=True)
        .values("description")
        .annotate(quantity=Sum("quantity"), revenue=Sum("line_total"), lines=Count("id"))
    )
    rows = [
        {"name": row["product__name"], "category": row["product__category__name"], **_totals(row)} for row in products
    ] + [{"name": row["description"], "category": "", **_totals(row)} for row in manual]
    rows.sort(key=lambda row: row["revenue"], reverse=True)
    return rows[:limit] if limit else rows


def _totals(row):
    return {"quantity": row["quantity"], "revenue": row["revenue"], "lines": row["lines"]}


def stock_value(branch_ids):
    rows = (
        BranchStock.objects.filter(branch_id__in=branch_ids, product__track_stock=True, quantity__gt=0)
        .values("branch__name")
        .annotate(
            items=Count("id"),
            cost=Coalesce(Sum(F("quantity") * F("product__cost_price"), output_field=MONEY), Value(ZERO), output_field=MONEY),
            retail=Coalesce(Sum(F("quantity") * F("product__price"), output_field=MONEY), Value(ZERO), output_field=MONEY),
        )
        .order_by("branch__name")
    )
    return list(rows)


def daily_sales_rows(start, end, branch_ids):
    """For the CSV export: one row per issued invoice."""
    return (
        Invoice.objects.filter(
            branch_id__in=branch_ids, status__in=[Invoice.ISSUED, Invoice.PAID], invoice_date__range=(start, end)
        )
        .select_related("branch", "client", "appointment")
        .order_by("invoice_date", "number")
    )

