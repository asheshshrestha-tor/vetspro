"""The admin-defined grids of a visit (history, examination, vaccination) and their history per pet.

Every visit shows every field that is in use, plus any retired field the visit
already has a value for. Only filled-in rows are stored.
"""
from apps.clinic_setup.models import ExaminationType, HistoryOption, VaccinationType

from .forms import ValueForm, VaccinationRowForm
from .models import Appointment, AppointmentHistory, ExaminationResult, VaccinationRecord


def field_list(model, used_ids):
    return list((model.objects.filter(is_active=True) | model.objects.filter(pk__in=used_ids)).distinct())


def previous_values(visit, model, field_name):
    """The latest earlier value of each field for this pet, as {field id: record}."""
    records = (
        model.objects.filter(appointment__pet=visit.pet)
        .exclude(appointment=visit)
        .exclude(appointment__status=Appointment.CANCELLED)
        .filter(appointment__visit_date__lte=visit.visit_date)
        .select_related("appointment")
        .order_by("-appointment__visit_date", "-appointment_id")
    )
    latest = {}
    for record in records:
        latest.setdefault(getattr(record, f"{field_name}_id"), record)
    return latest


def build_grids(visit, data=None):
    """Forms for the history, examination and vaccination grids of a visit."""
    history = {r.option_id: r for r in visit.history.all()}
    exams = {r.exam_type_id: r for r in visit.examinations.all()}
    vaccines = {r.vaccine_id: r for r in visit.vaccinations.all()}

    previous_history = previous_values(visit, AppointmentHistory, "option")
    previous_exams = previous_values(visit, ExaminationResult, "exam_type")
    previous_vaccines = previous_values(visit, VaccinationRecord, "vaccine")

    return {
        "history_forms": [
            ValueForm(
                data,
                definition=option,
                current=history[option.pk].value if option.pk in history else "",
                previous=previous_history.get(option.pk),
                prefix=f"history-{option.pk}",
            )
            for option in field_list(HistoryOption, history)
        ],
        "exam_forms": [
            ValueForm(
                data,
                definition=exam_type,
                current=exams[exam_type.pk].value if exam_type.pk in exams else "",
                previous=previous_exams.get(exam_type.pk),
                prefix=f"exam-{exam_type.pk}",
            )
            for exam_type in field_list(ExaminationType, exams)
        ],
        "vaccination_forms": [
            VaccinationRowForm(
                data,
                vaccine=vaccine,
                visit_date=visit.visit_date,
                record=vaccines.get(vaccine.pk),
                previous=previous_vaccines.get(vaccine.pk),
                prefix=f"vaccine-{vaccine.pk}",
            )
            for vaccine in field_list(VaccinationType, vaccines)
        ],
    }


def save_value_rows(visit, forms, model, field_name):
    existing = {getattr(r, f"{field_name}_id"): r for r in model.objects.filter(appointment=visit)}
    for form in forms:
        value = form.cleaned_data.get("value", "")
        record = existing.get(form.definition.pk)
        if value:
            if record is None:
                record = model(appointment=visit, **{field_name: form.definition})
            record.value = value
            record.save()
        elif record is not None:
            record.delete()


def save_vaccination_rows(visit, forms):
    existing = {r.vaccine_id: r for r in visit.vaccinations.all()}
    for form in forms:
        record = existing.get(form.vaccine.pk)
        if form.has_data():
            if record is None:
                record = VaccinationRecord(appointment=visit, vaccine=form.vaccine)
            for name in VaccinationRowForm.FIELDS:
                setattr(record, name, form.cleaned_data.get(name) or ("" if name in ("batch_number", "notes") else None))
            record.save()
        elif record is not None:
            record.delete()


def save_grids(visit, grids):
    save_value_rows(visit, grids["history_forms"], AppointmentHistory, "option")
    save_value_rows(visit, grids["exam_forms"], ExaminationResult, "exam_type")
    save_vaccination_rows(visit, grids["vaccination_forms"])


def grids_have_input(grids):
    rows = grids["history_forms"] + grids["exam_forms"]
    return any(form.cleaned_data.get("value") for form in rows) or any(
        form.has_data() for form in grids["vaccination_forms"]
    )


def pet_tracking(pet):
    """Each field's values across the pet's visits, newest visit first, for the pet's record."""
    visits = list(
        pet.appointments.exclude(status=Appointment.CANCELLED).order_by("-visit_date", "-id")
    )

    def table(model, field_name, definitions_model):
        records = model.objects.filter(appointment__pet=pet).exclude(appointment__status=Appointment.CANCELLED)
        by_visit = {}
        used = set()
        for record in records.select_related(field_name):
            by_visit.setdefault(record.appointment_id, {})[getattr(record, f"{field_name}_id")] = record
            used.add(getattr(record, f"{field_name}_id"))
        columns = [d for d in definitions_model.objects.filter(pk__in=used)]
        rows = [
            {"visit": visit, "cells": [by_visit.get(visit.pk, {}).get(column.pk) for column in columns]}
            for visit in visits
            if visit.pk in by_visit
        ]
        return {"columns": columns, "rows": rows}

    return {
        "exams": table(ExaminationResult, "exam_type", ExaminationType),
        "history": table(AppointmentHistory, "option", HistoryOption),
    }
