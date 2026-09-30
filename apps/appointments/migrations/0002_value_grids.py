from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0001_initial"),
        ("clinic_setup", "0003_alter_examinationtype_options_and_more"),
    ]

    operations = [
        migrations.RenameField("appointmenthistory", "notes", "value"),
        migrations.AlterField("appointmenthistory", "value", models.CharField(max_length=255)),
        migrations.AddField(
            "appointmenthistory",
            "is_abnormal",
            models.BooleanField(default=False, editable=False, verbose_name="outside normal"),
        ),
        migrations.AlterModelOptions("appointmenthistory", {
            "ordering": ["option__order", "option__name"],
            "verbose_name": "history entry",
            "verbose_name_plural": "history",
        }),
        migrations.AddField(
            "vaccinationrecord",
            "given_on",
            models.DateField(
                blank=True, null=True,
                help_text="When the dose was given. Earlier doses the owner reports can be recorded too.",
            ),
        ),
        migrations.AlterModelOptions("vaccinationrecord", {
            "ordering": ["vaccine__order", "vaccine__name"],
            "verbose_name": "vaccination",
        }),
        migrations.AddConstraint(
            "vaccinationrecord",
            models.UniqueConstraint(fields=("appointment", "vaccine"), name="vaccination_record_unique_vaccine"),
        ),
    ]
