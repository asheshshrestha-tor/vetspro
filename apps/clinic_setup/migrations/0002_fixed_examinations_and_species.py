from decimal import Decimal

from django.db import migrations

CONFIRM = "Starting range. Please confirm or correct it with the veterinary team."

EXAMINATIONS = [
    {"code": "temperature", "name": "Temperature", "value_kind": "number", "unit": "°C",
     "min_value": Decimal("37.5"), "max_value": Decimal("39.2")},
    {"code": "pulse", "name": "Pulse / heart rate", "value_kind": "number", "unit": "beats/min",
     "min_value": Decimal("60"), "max_value": Decimal("160")},
    {"code": "respiration", "name": "Respiration rate", "value_kind": "number", "unit": "breaths/min",
     "min_value": Decimal("10"), "max_value": Decimal("30")},
    {"code": "crt", "name": "Capillary refill time (CRT)", "value_kind": "number", "unit": "seconds",
     "min_value": Decimal("0"), "max_value": Decimal("2")},
    {"code": "anaemia", "name": "Anaemia (mucous membranes)", "value_kind": "choice",
     "options": "Pink\nPale\nWhite\nYellow\nBlue", "normal_options": "Pink"},
    {"code": "hydration", "name": "Hydration", "value_kind": "choice",
     "options": "Normal\nMild dehydration\nModerate dehydration\nSevere dehydration", "normal_options": "Normal"},
    {"code": "lymph_nodes", "name": "Lymph nodes", "value_kind": "choice",
     "options": "Normal\nEnlarged", "normal_options": "Normal"},
]

SPECIES = ["Dog", "Cat", "Rabbit", "Bird", "Other"]


def add_fixed_data(apps, schema_editor):
    ExaminationType = apps.get_model("clinic_setup", "ExaminationType")
    Species = apps.get_model("clinic_setup", "Species")
    for order, spec in enumerate(EXAMINATIONS):
        ExaminationType.objects.get_or_create(
            code=spec["code"], defaults={**spec, "order": order, "description": CONFIRM}
        )
    for name in SPECIES:
        Species.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("clinic_setup", "0001_initial")]

    operations = [migrations.RunPython(add_fixed_data, migrations.RunPython.noop)]
