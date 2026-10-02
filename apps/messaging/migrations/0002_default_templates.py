"""Starter wording for messages to owners. Staff change it under Clinic setup → Message templates."""
from django.db import migrations

TEMPLATES = [
    ("Vaccination reminder", "vaccination_due", "Vaccination reminder for {pet}",
     "Namaste {client}, this is a reminder from {hospital}: {pet}'s {vaccine} vaccination is due on {date}. "
     "Please visit us or call {phone} to book. Thank you!"),
    ("Visit reminder", "follow_up", "Visit reminder for {pet}",
     "Namaste {client}, {pet} is due for a check-up at {hospital} ({branch}) on {date}. Call {phone} if you need to change it."),
    ("Booking confirmation", "booking", "Booking confirmed for {pet}",
     "Namaste {client}, {pet}'s visit at {hospital} ({branch}) is booked for {date} {time}. Call {phone} to change it."),
    ("Bill", "invoice", "Your bill {invoice}",
     "Namaste {client}, your bill {invoice} from {hospital} is {amount}. Balance due: {balance}. Thank you!"),
    ("General message", "general", "Message from {hospital}", "Namaste {client}, "),
]


def add(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    for name, purpose, subject, body in TEMPLATES:
        MessageTemplate.objects.get_or_create(name=name, defaults={"purpose": purpose, "subject": subject, "body": body})


class Migration(migrations.Migration):
    dependencies = [("messaging", "0001_initial")]

    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
