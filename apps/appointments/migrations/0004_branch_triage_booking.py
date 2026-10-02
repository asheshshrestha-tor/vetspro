import django.db.models.deletion
from django.db import migrations, models


def to_main_branch(apps, schema_editor):
    Branch = apps.get_model("branches", "Branch")
    Appointment = apps.get_model("appointments", "Appointment")
    main = Branch.objects.order_by("-is_main", "id").first()
    if main is not None:
        Appointment.objects.filter(branch__isnull=True).update(branch=main)


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0003_treatment_item_treatment_quantity_and_more"),
        ("branches", "0002_main_branch"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="branch",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to="branches.branch"
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="priority",
            field=models.CharField(
                choices=[("emergency", "Emergency"), ("urgent", "Urgent"), ("routine", "Routine")],
                db_index=True, default="routine",
                help_text="Emergency and urgent cases go to the top of the queue.", max_length=10, verbose_name="triage",
            ),
        ),
        migrations.AddField(
            model_name="appointment",
            name="scheduled_time",
            field=models.TimeField(
                blank=True, null=True, help_text="For booked visits; walk-ins join the queue by token.",
                verbose_name="booked time",
            ),
        ),
        migrations.RemoveConstraint(model_name="appointment", name="appointment_unique_daily_token"),
        migrations.RunPython(to_main_branch, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="appointment",
            name="branch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to="branches.branch"
            ),
        ),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("token__isnull", False)), fields=("branch", "visit_date", "token"),
                name="appointment_unique_branch_daily_token",
            ),
        ),
    ]
