from apps.dashboard.registry import Module, site

from . import views
from .models import Report


@site.register(Report)
class ReportModule(Module):
    group = "Billing"
    icon = "ki-chart-line-up"
    name = "report"
    name_plural = "reports"
    description = "Sales, payments, visits, vets' work and best-selling items for any period, by branch."
    menu_order = 30
    show_on_home = False
    can_add = False
    can_change = False
    can_delete = False

    list_display = ["id"]  # the list page is replaced by the report
    fields = []
    views = {"list": views.ReportsView}
