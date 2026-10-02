import csv
import datetime

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import TemplateView

from apps.branches.context import current_branch, scope_ids
from apps.dashboard.mixins import ModuleMixin

from . import data

PERIODS = [
    ("today", "Today"),
    ("7", "Last 7 days"),
    ("30", "Last 30 days"),
    ("month", "This month"),
    ("last_month", "Last month"),
    ("year", "This year"),
]


def period_range(request):
    """The dates to report on, from ?period= or ?start=&end=."""
    today = timezone.localdate()
    start, end = parse_date(request.GET.get("start") or ""), parse_date(request.GET.get("end") or "")
    if start and end:
        if start > end:
            start, end = end, start
        return "custom", start, min(end, start + datetime.timedelta(days=366))
    period = request.GET.get("period", "30")
    if period == "today":
        return period, today, today
    if period == "7":
        return period, today - datetime.timedelta(days=6), today
    if period == "month":
        return period, today.replace(day=1), today
    if period == "last_month":
        last = today.replace(day=1) - datetime.timedelta(days=1)
        return period, last.replace(day=1), last
    if period == "year":
        return period, today.replace(month=1, day=1), today
    return "30", today - datetime.timedelta(days=29), today


class ReportsView(ModuleMixin, TemplateView):
    template_name = "reports/reports.html"

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        period, self.start, self.end = period_range(request)
        self.period = period
        self.branch_ids = scope_ids(request)
        export = request.GET.get("export", "")
        if export:
            return self.export(export)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end, ids = self.start, self.end, self.branch_ids
        sales = data.sales(start, end, ids)
        visits = data.visits(start, end, ids)
        context.update(
            period=self.period,
            periods=PERIODS,
            start=start,
            end=end,
            branch=current_branch(self.request),
            many_branches=len(ids) > 1,
            sales=sales,
            visits=visits,
            providers=data.providers(start, end, ids),
            top_items=data.top_items(start, end, ids),
            stock=data.stock_value(ids),
            can_see_money=self.request.user.has_perm("billing.view_invoice"),
            chart={
                "labels": [f"{row['date']:%d %b}" for row in sales["daily"]],
                "sales": [float(row["value"]) for row in sales["daily"]],
                "visits": [row["value"] for row in visits["daily"]],
            },
            query=self.request.GET.urlencode(),
        )
        return context

    def export(self, kind):
        start, end, ids = self.start, self.end, self.branch_ids
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{kind}-{start:%Y%m%d}-{end:%Y%m%d}.csv"'
        response.write("﻿")  # so Excel reads it as UTF-8
        writer = csv.writer(response)
        if kind == "sales":
            self.require(self.request.user.has_perm("billing.view_invoice"))
            writer.writerow(["Date", "Invoice", "Branch", "Customer", "Visit", "Subtotal", "Discount", "VAT", "Total", "Paid", "Balance", "Status"])
            for invoice in data.daily_sales_rows(start, end, ids):
                writer.writerow([
                    invoice.invoice_date, invoice.number, invoice.branch.name, invoice.customer_display,
                    invoice.appointment.number if invoice.appointment_id else "", invoice.subtotal, invoice.discount,
                    invoice.vat_amount, invoice.total, invoice.amount_paid, invoice.balance, invoice.payment_label,
                ])
        elif kind == "items":
            self.require(self.request.user.has_perm("billing.view_invoice"))
            writer.writerow(["Item", "Category", "Quantity", "Revenue", "Lines"])
            for row in data.top_items(start, end, ids, limit=None):
                writer.writerow([row["name"], row["category"], row["quantity"], row["revenue"], row["lines"]])
        elif kind == "providers":
            writer.writerow(["Vet", "Visits", "Completed", "Billed"])
            for row in data.providers(start, end, ids):
                writer.writerow([row["name"], row["visits"], row["completed"], row["billed"]])
        else:
            writer.writerow(["Date", "Visits"])
            for row in data.visits(start, end, ids)["daily"]:
                writer.writerow([row["date"], row["value"]])
        return response
