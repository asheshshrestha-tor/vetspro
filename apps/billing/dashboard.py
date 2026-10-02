from django.db.models import Count, Q, Sum
from django.urls import path, reverse
from django.utils import timezone

from apps.branches.context import scope_ids
from apps.clients.models import normalize_phone
from apps.dashboard.registry import Action, Badge, Module, site

from . import views
from .models import Invoice, Payment


@site.register(Invoice)
class InvoiceModule(Module):
    group = "Billing"
    icon = "ki-bill"
    description = "Bills for counter sales and visits. A draft becomes an invoice with a number when it is issued."
    menu_order = 10
    branch_field = "branch"

    list_display = ["number_or_draft", "invoice_date", "customer", "visit", "amount", "status_badge"]
    search_fields = ["number", "client__full_name", "client__phone", "customer_name", "customer_phone", "appointment__number"]
    list_filter = ["status", "branch"]
    date_filter = "invoice_date"
    per_page = 25

    views = {"add": views.NewSaleView, "edit": views.InvoiceView}

    def get_queryset(self):
        return Invoice.objects.select_related("branch", "client", "appointment")

    def search_conditions(self, term):
        conditions = super().search_conditions(term)
        digits = normalize_phone(term)
        if len(digits) >= 4:
            conditions.append(Q(client__phone_digits__contains=digits))
        return conditions

    def get_urls(self):
        return [
            path("<int:pk>/print/", views.InvoicePrintView.as_view(), name="invoice_print"),
            path("<int:pk>/receipt/<int:payment_pk>/", views.PaymentReceiptView.as_view(), name="invoice_receipt"),
            path("<int:pk>/pay/", views.InvoiceActionView.as_view(), {"action": "pay"}, name="invoice_pay"),
            path("<int:pk>/cancel/", views.InvoiceActionView.as_view(), {"action": "cancel"}, name="invoice_cancel"),
            path("visit/<int:appointment_pk>/", views.VisitInvoiceView.as_view(), name="invoice_for_visit"),
        ]

    def menu_items(self, request=None):
        return [
            {"title": "New sale", "url": self.add_url, "icon": "ki-handcart", "badge": None, "url_names": ["add"]},
            {"title": self.title, "url": self.list_url, "icon": self.icon, "badge": None, "url_names": []},
        ]

    def has_object_permission(self, user, obj, action):
        # Issued invoices are cancelled, never deleted, so the numbering stays complete.
        if action == "delete":
            return obj.is_draft
        return True

    def row_actions(self, obj, request):
        if obj.is_draft:
            return []
        return [Action("", reverse("dashboard:invoice_print", args=[obj.pk]), icon="ki-printer", color="light",
                       preview=True, title=obj.display_number)]

    def number_or_draft(self, obj):
        return obj.display_number

    number_or_draft.short_description = "Invoice"

    def customer(self, obj):
        return obj.customer_display

    customer.short_description = "Customer"

    def visit(self, obj):
        return obj.appointment.number if obj.appointment_id else ""

    visit.short_description = "Visit"

    def amount(self, obj):
        return f"Rs. {obj.total:,.2f}"

    amount.short_description = "Total"

    def status_badge(self, obj):
        label = obj.payment_label
        color = {"Paid": "success", "Partly paid": "warning", "Unpaid": "danger"}.get(label, obj.status_color)
        return Badge(label, color)

    status_badge.short_description = "Status"

    def home_panel(self, request):
        today = timezone.localdate()
        invoices = Invoice.objects.filter(branch_id__in=scope_ids(request))
        issued_today = invoices.filter(invoice_date=today, status__in=[Invoice.ISSUED, Invoice.PAID])
        unpaid = invoices.filter(status=Invoice.ISSUED)
        payments_today = Payment.objects.filter(
            received_at__date=today, invoice__in=invoices, invoice__status__in=[Invoice.ISSUED, Invoice.PAID]
        )
        return (
            "billing/home_panel.html",
            {
                "sales_total": issued_today.aggregate(total=Sum("total"))["total"] or 0,
                "sales_count": issued_today.count(),
                "received": payments_today.aggregate(total=Sum("amount"))["total"] or 0,
                "by_method": payments_today.values("method").annotate(total=Sum("amount"), count=Count("id")).order_by("-total"),
                "unpaid_count": unpaid.count(),
                "unpaid_total": sum(invoice.balance for invoice in unpaid),
                "recent": invoices.exclude(status=Invoice.DRAFT).select_related("client")[:6],
                "drafts": invoices.filter(status=Invoice.DRAFT).count(),
                "can_add": self.user_can_add(request.user),
                "methods": dict(Payment.METHODS),
            },
        )
