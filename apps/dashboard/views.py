import datetime
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.exceptions import FieldDoesNotExist
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Count, ProtectedError
from django.db.models.functions import TruncDate
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.contact.models import ContactMessage
from apps.core.models import SiteSettings
from apps.gallery.models import GalleryImage
from apps.team.models import TeamMember
from apps.testimonials.models import Testimonial

from .cells import build_cell, column_label, object_label, resolve_field
from .forms import LoginForm, StyledPasswordChangeForm, build_form, build_inline_formsets
from .mixins import ModuleMixin, StaffRequiredMixin
from .registry import site


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return fallback


class LoginView(auth_views.LoginView):
    template_name = "dashboard/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard:home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Django's login view sets "site" to the current host; the templates expect the hospital's settings.
        context["site"] = SiteSettings.load()
        return context


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("dashboard:login")


class PasswordChangeView(StaffRequiredMixin, auth_views.PasswordChangeView):
    template_name = "dashboard/password.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("dashboard:home")

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)


class HomeView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"
    chart_days = 14

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        visible = site.modules(user)

        cards = [
            {"module": module, "count": module.queryset_for(self.request).count()}
            for modules in site.grouped(user).values()
            for module in modules
            if not module.singleton and module.show_on_home
        ]
        panels = [panel for panel in (module.home_panel(self.request) for module in visible) if panel]

        context.update(cards=cards, panels=panels)

        # The website checklist is only useful to people who manage the website.
        settings_module = site.for_model(SiteSettings)
        if settings_module and settings_module.can_view(user):
            context["checklist"] = self.get_checklist()

        inbox = site.for_model(ContactMessage)
        if inbox and inbox.can_view(user):
            context.update(
                inbox=inbox,
                unread_count=ContactMessage.objects.filter(is_read=False).count(),
                recent_messages=ContactMessage.objects.all()[:6],
                chart=self.get_chart(),
            )
        return context

    def get_chart(self):
        today = timezone.localdate()
        start = today - datetime.timedelta(days=self.chart_days - 1)
        counts = dict(
            ContactMessage.objects.filter(created_at__date__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values_list("day")
            .annotate(total=Count("id"))
        )
        days = [start + datetime.timedelta(days=i) for i in range(self.chart_days)]
        return {
            "labels": [day.strftime("%d %b") for day in days],
            "values": [counts.get(day, 0) for day in days],
            "total": sum(counts.values()),
        }

    def get_checklist(self):
        """What is still missing before the public site is complete."""
        settings = SiteSettings.load()
        user = self.request.user

        def module_url(model):
            module = site.for_model(model)
            return module.list_url if module and module.can_view(user) else ""

        settings_url = module_url(SiteSettings)

        items = [
            ("Email address", bool(settings.email), settings_url),
            ("Hospital address", bool(settings.address), settings_url),
            ("Facebook page link", bool(settings.facebook_url), settings_url),
            ("Map on the contact page", bool(settings.map_embed_url), settings_url),
            ("Team profiles", TeamMember.objects.active().exists(), module_url(TeamMember)),
            ("Gallery photos", GalleryImage.objects.active().exists(), module_url(GalleryImage)),
            ("Client testimonials", Testimonial.objects.active().exists(), module_url(Testimonial)),
        ]
        done = sum(1 for _, complete, _ in items if complete)
        return {
            "items": [{"label": label, "done": complete, "url": url} for label, complete, url in items],
            "done": done,
            "total": len(items),
            "percent": round(done * 100 / len(items)),
        }


DATE_RANGES = [("today", "Today"), ("week", "This week"), ("month", "This month")]


class ModuleListView(ModuleMixin, TemplateView):
    template_name = "dashboard/list.html"

    def get_template_names(self):
        return [self.module.list_template or self.template_name]

    def get(self, request, *args, **kwargs):
        self.require(self.module.can_view(request.user))
        if self.module.singleton:
            return redirect(self.module.url("edit", self.module.get_singleton().pk))
        return super().get(request, *args, **kwargs)

    def get_filters(self):
        filters = []
        for name in self.module.list_filter:
            # A module method with `filter_choices` filters the list itself, e.g. by stock level.
            method = getattr(self.module, name, None)
            if callable(method) and hasattr(method, "filter_choices"):
                choices = list(method.filter_choices)
                selected = self.request.GET.get(name, "")
                if selected not in dict(choices):
                    selected = ""
                filters.append({"name": name, "label": column_label(self.module, name), "choices": choices,
                                "selected": selected, "method": method})
                continue
            field = resolve_field(self.module.model, name)
            if isinstance(field, models.BooleanField):
                choices = [("1", "Yes"), ("0", "No")]
            elif field.is_relation:
                related = field.related_model._default_manager.complex_filter(field.get_limit_choices_to())
                choices = [(str(obj.pk), object_label(obj)) for obj in related]
            else:
                choices = [(str(value), label) for value, label in field.flatchoices]
            selected = self.request.GET.get(name, "")
            if selected not in dict(choices):
                selected = ""
            filters.append({"name": name, "label": column_label(self.module, name), "choices": choices, "selected": selected})
        return filters

    def get_date_range(self):
        """The (start, end, preset) chosen with the list's date filter."""
        if not self.module.date_filter:
            return None
        get = self.request.GET
        today = timezone.localdate()
        preset = get.get("period", "")
        start = end = None
        if preset == "today":
            start = end = today
        elif preset == "week":
            start = today - datetime.timedelta(days=today.weekday())
            end = start + datetime.timedelta(days=6)
        elif preset == "month":
            start = today.replace(day=1)
            end = (start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
        else:
            preset = ""
            start = parse_date(get.get("date_from", "") or "") if get.get("date_from") else None
            end = parse_date(get.get("date_to", "") or "") if get.get("date_to") else None
        return {"start": start, "end": end, "preset": preset, "presets": DATE_RANGES,
                "label": column_label(self.module, self.module.date_filter)}

    def get_queryset(self, filters, date_range):
        module = self.module
        queryset = module.queryset_for(self.request)

        related = []
        for name in module.list_display:
            try:
                field = module.opts.get_field(name)
            except FieldDoesNotExist:
                continue
            if field.many_to_one:
                related.append(name)
        if related:
            queryset = queryset.select_related(*related)

        for item in filters:
            if not item["selected"]:
                continue
            if "method" in item:
                queryset = item["method"](self.request, queryset, item["selected"])
                continue
            field = resolve_field(module.model, item["name"])
            value = item["selected"] == "1" if isinstance(field, models.BooleanField) else item["selected"]
            queryset = queryset.filter(**{item["name"]: value})

        if date_range:
            lookup = module.date_filter
            if isinstance(resolve_field(module.model, lookup), models.DateTimeField):
                lookup += "__date"
            if date_range["start"]:
                queryset = queryset.filter(**{f"{lookup}__gte": date_range["start"]})
            if date_range["end"]:
                queryset = queryset.filter(**{f"{lookup}__lte": date_range["end"]})

        self.query = self.request.GET.get("q", "").strip()
        return module.apply_search(queryset, self.query)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = self.module
        filters = self.get_filters()
        date_range = self.get_date_range()
        queryset = self.get_queryset(filters, date_range)

        page = Paginator(queryset, module.per_page).get_page(self.request.GET.get("page"))
        user = self.request.user
        rows = []
        for obj in page:
            cells = [build_cell(module, obj, name) for name in module.list_display]
            # The first piece of text in the row opens the record.
            title = next((cell for cell in cells if cell["kind"] == "text"), None)
            if title:
                title["kind"] = "title"
            rows.append(
                {
                    "object": obj,
                    "url": module.object_url(obj),
                    "delete_url": module.url("delete", obj.pk),
                    "can_delete": module.has_object_permission(user, obj, "delete"),
                    "actions": module.row_actions(obj, self.request),
                    "cells": cells,
                }
            )

        params = self.request.GET.copy()
        params.pop("page", None)

        context.update(
            columns=[column_label(module, name) for name in module.list_display],
            rows=rows,
            page=page,
            page_range=page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1),
            query=self.query,
            filters=filters,
            date_range=date_range,
            is_filtered=bool(
                self.query
                or any(f["selected"] for f in filters)
                or (date_range and (date_range["start"] or date_range["end"]))
            ),
            querystring=params.urlencode(),
        )
        return context


class ModuleFormView(ModuleMixin, TemplateView):
    """Adds a record, edits one, or shows it read-only when editing is not allowed."""

    template_name = "dashboard/form.html"
    detail_template_name = "dashboard/detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def load_object(self):
        pk = self.kwargs.get("pk")
        if pk is None:
            self.require(self.module.user_can_add(self.request.user))
            return None
        return get_object_or_404(self.module.access_queryset(self.request), pk=pk)

    @property
    def read_only(self):
        if self.object is None:
            return False
        user = self.request.user
        return not (
            self.module.user_can_change(user) and self.module.has_object_permission(user, self.object, "change")
        )

    def get_template_names(self):
        if self.read_only:
            return [self.module.detail_template or self.detail_template_name]
        return [self.module.form_template or self.template_name]

    def build_form(self, data=None, files=None):
        form_class = build_form(self.module)
        kwargs = {"instance": self.object, "request": self.request, **self.module.form_kwargs(self.request, self.object)}
        return form_class(data, files, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object = self.load_object()
        if self.read_only:
            self.require(self.module.can_view(request.user))
            self.module.on_view(self.object)
            return self.render_to_response(self.get_context_data())
        form = self.build_form()
        formsets = build_inline_formsets(self.module, self.object)
        return self.render_to_response(self.get_context_data(form=form, formsets=formsets))

    def post(self, request, *args, **kwargs):
        self.object = self.load_object()
        if self.object is not None:
            self.require(not self.read_only)

        form = self.build_form(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                saved = form.save(commit=False)
                formsets = build_inline_formsets(self.module, saved, request.POST, request.FILES)
                if all(formset.is_valid() for formset in formsets):
                    self.module.assign_branch(request, saved)
                    self.module.save_model(request, saved, form, change=self.object is not None)
                    saved.save()
                    form.save_m2m()
                    for formset in formsets:
                        formset.save()
                    self.module.after_save(request, saved, form, change=self.object is not None)
                    return self.saved(saved)
        else:
            formsets = build_inline_formsets(self.module, self.object, request.POST, request.FILES)

        messages.error(request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form, formsets=formsets))

    def saved(self, obj):
        action = "updated" if self.kwargs.get("pk") else "added"
        messages.success(self.request, f"{self.module.singular.capitalize()} “{obj}” was {action}.")
        if "_continue" in self.request.POST or self.module.singleton:
            return redirect(self.module.url("edit", obj.pk))
        if "_addanother" in self.request.POST and self.module.user_can_add(self.request.user):
            return redirect(self.module.add_url)
        return redirect(safe_next(self.request, self.module.list_url))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.object
        context.update(self.module.extra_context(self.request, self.object))
        if self.object is not None:
            context["can_delete"] = context["can_delete"] and self.module.has_object_permission(
                self.request.user, self.object, "delete"
            )
        if self.read_only:
            names = self.module.get_fields()
            context["details"] = [
                {"label": column_label(self.module, name), "cell": build_cell(self.module, self.object, name, truncate=None)}
                for name in names
            ]
        return context


class ModuleDeleteView(ModuleMixin, TemplateView):
    template_name = "dashboard/confirm_delete.html"

    def get_object(self):
        self.require(self.module.user_can_delete(self.request.user))
        obj = get_object_or_404(self.module.access_queryset(self.request), pk=self.kwargs["pk"])
        self.require(self.module.has_object_permission(self.request.user, obj, "delete"))
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(object=self.object))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        label = str(self.object)
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(request, f"“{label}” is used elsewhere and cannot be deleted. Mark it inactive instead.")
        else:
            messages.success(request, f"{self.module.singular.capitalize()} “{label}” was deleted.")
        return redirect(self.module.list_url)


class ModuleToggleView(ModuleMixin, View):
    """Switches one of the module's toggle fields on or off."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        self.require(self.module.user_can_toggle(request.user))
        field = kwargs["field"]
        if field not in self.module.toggle_fields:
            raise Http404("This field cannot be toggled.")

        obj = get_object_or_404(self.module.access_queryset(self.request), pk=kwargs["pk"])
        self.require(self.module.has_object_permission(request.user, obj, "change"))
        setattr(obj, field, not getattr(obj, field))
        obj.save(update_fields=[field] + (["updated_at"] if hasattr(obj, "updated_at") else []))
        return redirect(safe_next(request, self.module.list_url))


class AutocompleteView(ModuleMixin, View):
    """JSON search used by the search-as-you-type dropdowns."""

    limit = 20

    def get(self, request, *args, **kwargs):
        module = self.module
        self.require(module.can_view(request.user))
        queryset = module.autocomplete_queryset(request)

        for name in module.autocomplete_filters:
            value = request.GET.get(name, "")
            if value:
                if not value.isdigit():
                    return JsonResponse({"results": []})
                queryset = queryset.filter(**{f"{name}_id": value})

        queryset = module.apply_search(queryset, request.GET.get("q", "").strip())
        results = [
            {**module.autocomplete_data(obj, request), "id": obj.pk, "text": module.autocomplete_label(obj, request)}
            for obj in queryset[: self.limit]
        ]
        return JsonResponse({"results": results})


def module_view(name, default):
    """Routes a generic page to the module's own view when it provides one."""
    default_view = default.as_view()
    cache = {}

    def view(request, *args, **kwargs):
        module = site.get(kwargs.get("app_label"), kwargs.get("model_name"))
        view_class = module.views.get(name) if module else None
        if view_class is None:
            return default_view(request, *args, **kwargs)
        if view_class not in cache:
            cache[view_class] = view_class.as_view()
        return cache[view_class](request, *args, **kwargs)

    return view

