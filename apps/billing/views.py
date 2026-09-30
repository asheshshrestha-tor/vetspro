from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.appointments.models import Appointment
from apps.clients.models import Client
from apps.dashboard.mixins import ModuleMixin

from .forms import InvoiceForm, InvoiceItemFormSet, NewSaleForm, PaymentForm
from .models import Invoice, InvoiceItem, Payment
from .services import build_visit_bill, current_visit_bill, new_invoice


class InvoicePage(ModuleMixin):
    def setup(self, request, *args, **kwargs):
        kwargs.setdefault("app_label", "billing")
        kwargs.setdefault("model_name", "invoice")
        super().setup(request, *args, **kwargs)

    def get_invoice(self):
        return get_object_or_404(
            Invoice.objects.select_related("client", "appointment__pet", "created_by", "issued_by"), pk=self.kwargs["pk"]
        )


class NewSaleView(InvoicePage, TemplateView):
    """Start a bill for someone buying at the counter, with or without a client record or visit."""

    template_name = "billing/new_sale.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        initial = {}
        client_id = request.GET.get("client", "")
        if client_id.isdigit() and Client.objects.filter(pk=client_id).exists():
            initial["client"] = int(client_id)
        return self.render_to_response(self.get_context_data(form=NewSaleForm(initial=initial, request=request)))

    def post(self, request, *args, **kwargs):
        self.require(self.module.user_can_add(request.user))
        form = NewSaleForm(request.POST, request=request)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        data = form.cleaned_data
        invoice = new_invoice(
            request.user,
            client=data.get("client"),
            customer_name=data.get("customer_name", "").strip(),
            customer_phone=data.get("customer_phone", "").strip(),
        )
        return redirect(invoice.get_absolute_url())


class InvoiceView(InvoicePage, TemplateView):
    """The bill: items and totals while it is a draft, then payments, printing and cancelling."""

    template_name = "billing/invoice.html"

    def load(self):
        self.invoice = self.get_invoice()
        user = self.request.user
        self.require(self.module.can_view(user))
        self.can_edit = self.invoice.is_draft and self.module.user_can_change(user)

    def build_forms(self, data=None):
        if not self.can_edit:
            return {}
        return {
            "form": InvoiceForm(data, instance=self.invoice, prefix="invoice", request=self.request),
            "formset": InvoiceItemFormSet(
                data, instance=self.invoice, prefix="items",
                queryset=self.invoice.items.filter(source=InvoiceItem.MANUAL),
            ),
        }

    def get(self, request, *args, **kwargs):
        self.load()
        return self.render_to_response(self.get_context_data(**self.build_forms()))

    def post(self, request, *args, **kwargs):
        self.load()
        self.require(self.can_edit)
        forms = self.build_forms(request.POST)
        issue = "_issue" in request.POST and request.user.has_perm("billing.issue_invoice")
        paid_by = request.POST.get("paid_by", "")
        if paid_by not in dict(Payment.METHODS) or not request.user.has_perm("billing.record_payment"):
            paid_by = ""
        if forms["form"].is_valid() and forms["formset"].is_valid():
            try:
                with transaction.atomic():
                    forms["form"].save()
                    forms["formset"].save()
                    self.invoice.recalculate()
                    if issue:
                        self.invoice.issue(request.user)
                        if paid_by and self.invoice.total > 0:
                            self.invoice.add_payment(self.invoice.total, paid_by, request.user)
            except ValidationError as error:
                # Nothing was saved; show why, e.g. not enough stock.
                messages.error(request, " ".join(error.messages))
                return self.render_to_response(self.get_context_data(**forms))
            if issue:
                message = f"Invoice {self.invoice.number} issued for Rs. {self.invoice.total:,.2f}"
                if paid_by and self.invoice.total > 0:
                    message += f" and paid by {dict(Payment.METHODS)[paid_by]}"
                messages.success(request, message + ".")
            else:
                messages.success(request, "Draft saved.")
            return redirect(self.invoice.get_absolute_url())
        messages.error(request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(**forms))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.invoice
        user = self.request.user
        context.update(
            invoice=invoice,
            object=invoice,
            items=invoice.items.select_related("product"),
            visit_items=invoice.items.exclude(source=InvoiceItem.MANUAL).select_related("product", "treatment"),
            visit_total=sum(item.line_total for item in invoice.items.exclude(source=InvoiceItem.MANUAL)),
            visit_fee_line=invoice.items.filter(source=InvoiceItem.VISIT_FEE).exists(),
            payment_methods=Payment.METHODS,
            can_take_payment=user.has_perm("billing.record_payment"),
            payments=invoice.payments.select_related("received_by"),
            can_edit=self.can_edit,
            can_issue=self.can_edit and user.has_perm("billing.issue_invoice"),
            can_pay=invoice.status == Invoice.ISSUED and user.has_perm("billing.record_payment"),
            can_cancel=invoice.status in (Invoice.ISSUED, Invoice.PAID) and user.has_perm("billing.cancel_invoice"),
            payment_form=PaymentForm(invoice=invoice, prefix="payment"),
            back_url=invoice.appointment.get_absolute_url() if invoice.appointment_id else self.module.list_url,
        )
        return context


class InvoiceActionView(InvoicePage, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        invoice = self.get_invoice()
        action = kwargs["action"]
        try:
            if action == "cancel":
                self.require(request.user.has_perm("billing.cancel_invoice"))
                invoice.cancel(request.user, request.POST.get("reason", "").strip())
                message = f"Invoice {invoice.number} was cancelled and its items returned to stock."
                if invoice.amount_paid:
                    message += f" Refund Rs. {invoice.amount_paid:,.2f} to the customer."
                messages.success(request, message)
            elif action == "pay":
                self.require(request.user.has_perm("billing.record_payment"))
                form = PaymentForm(request.POST, prefix="payment", invoice=invoice)
                if not form.is_valid():
                    raise ValidationError(" ".join(e for errors in form.errors.values() for e in errors))
                data = form.cleaned_data
                invoice.add_payment(data["amount"], data["method"], request.user, data.get("reference", ""))
                messages.success(request, f"Payment of Rs. {data['amount']:,.2f} recorded. {invoice.payment_label}.")
            else:
                raise Http404("Unknown action.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        return redirect(invoice.get_absolute_url())


class InvoicePrintView(InvoicePage, TemplateView):
    template_name = "billing/print.html"

    def get(self, request, *args, **kwargs):
        self.invoice = self.get_invoice()
        self.require(self.module.can_view(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            invoice=self.invoice,
            items=self.invoice.items.all(),
            payments=self.invoice.payments.all(),
        )
        return context


class VisitInvoiceView(InvoicePage, View):
    """Build the visit's bill from its treatments, or open it once it has been issued."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        visit = get_object_or_404(Appointment.objects.select_related("client"), pk=kwargs["appointment_pk"])
        existing = current_visit_bill(visit)
        if existing is not None and not existing.is_draft:
            self.require(self.module.can_view(request.user))
            return redirect(existing.get_absolute_url())
        self.require(
            self.module.user_can_add(request.user) if existing is None else self.module.user_can_change(request.user)
        )
        invoice, created = build_visit_bill(visit, request.user)
        count = invoice.items.exclude(source=InvoiceItem.MANUAL).count()
        if created:
            messages.success(request, f"Bill started for {visit.number} with {count} item{'s' if count != 1 else ''} from the visit.")
        else:
            messages.success(request, "Bill updated from the visit's treatment.")
        return redirect(invoice.get_absolute_url())
