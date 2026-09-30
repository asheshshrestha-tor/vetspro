"""Make the default visit fields match the hospital's paper registration form.

Only fields that do not exist yet are added, and existing ones are updated by
code, so running this on a database where staff have edited the lists is safe.
"""
from django.db import migrations

CONFIRM = "Starting range. Please confirm or correct it with the veterinary team."

EXAMINATIONS = [
    # code, name, kind, extra fields
    ("temperature", "Temperature", "number", {}),
    ("respiration", "Respiration rate", "number", {}),
    ("pulse", "Pulse / heart rate", "number", {}),
    ("mucous_membranes", "Mucous membranes (M.M.)", "choice",
     {"options": "Pink\nPale\nCongested\nYellow\nBlue", "normal_options": "Pink"}),
    ("skin", "Skin", "text", {}),
    ("crt", "Capillary refill time (CRT)", "number", {}),
    ("anaemia", "Anaemia", "choice",
     {"options": "None\nMild\nModerate\nSevere", "normal_options": "None"}),
    ("vomiting_diarrhoea", "Vomiting / Diarrhoea", "choice",
     {"options": "None\nVomiting\nDiarrhoea\nBoth", "normal_options": "None"}),
    ("hydration", "Dehydration", "choice",
     {"options": "None\nMild\nModerate\nSevere", "normal_options": "None"}),
]

HISTORY = ["Vomiting / Diarrhoea", "Respiration", "Anorexia", "Skin", "Inappetence", "External parasites"]
VACCINES = ["Rabies", "DHPPiL", "Corona", "Deworming"]
SPECIES_ORDER = {"Dog": 0, "Cat": 1, "Rabbit": 2, "Bird": 3, "Other": 9}


def apply_paper_form(apps, schema_editor):
    ExaminationType = apps.get_model("clinic_setup", "ExaminationType")
    HistoryOption = apps.get_model("clinic_setup", "HistoryOption")
    VaccinationType = apps.get_model("clinic_setup", "VaccinationType")
    Species = apps.get_model("clinic_setup", "Species")

    for order, (code, name, kind, extra) in enumerate(EXAMINATIONS):
        exam = ExaminationType.objects.filter(code=code).first()
        if exam is None:
            exam = ExaminationType(code=code, description=CONFIRM if kind == "number" else "")
        exam.name, exam.value_kind, exam.order, exam.is_active = name, kind, order, True
        for field, value in extra.items():
            setattr(exam, field, value)
        exam.save()

    # Not on the paper form: kept for existing records, but hidden from new visits.
    ExaminationType.objects.filter(code="lymph_nodes").update(is_active=False, order=50)

    for order, name in enumerate(HISTORY):
        HistoryOption.objects.get_or_create(name=name, defaults={"order": order, "value_kind": "text"})
    for order, name in enumerate(VACCINES):
        VaccinationType.objects.get_or_create(name=name, defaults={"order": order})
    for name, order in SPECIES_ORDER.items():
        Species.objects.filter(name=name).update(order=order)


class Migration(migrations.Migration):
    dependencies = [("clinic_setup", "0003_alter_examinationtype_options_and_more")]

    operations = [migrations.RunPython(apply_paper_form, migrations.RunPython.noop)]
