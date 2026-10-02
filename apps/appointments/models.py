import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Exists, Max, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel


class AppointmentQuerySet(models.QuerySet):
    def on(self, day):
        return self.filter(visit_date=day)

    def in_queue(self):
        return self.filter(status__in=[Appointment.WAITING, Appointment.IN_CONSULTATION])


class Appointment(TimeStampedModel):
    """One visit of one pet, at one time. Walk-ins join the day's queue with a token number."""

    SCHEDULED = "scheduled"
    WAITING = "waiting"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (SCHEDULED, "Scheduled"),
        (WAITING, "Waiting"),
        (IN_CONSULTATION, "In consultation"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
    ]
    STATUS_COLORS = {
        SCHEDULED: "info",
        WAITING: "warning",
        IN_CONSULTATION: "primary",
        COMPLETED: "success",
        CANCELLED: "danger",
    }

    OUTCOME_CHOICES = [
        ("resolved", "Resolved"),
        ("improving", "Improving"),
        ("ongoing", "Ongoing treatment"),
        ("referred", "Referred"),
        ("deceased", "Deceased"),
    ]

    # action: (statuses it can start from, status it leads to)
    TRANSITIONS = {
        "check_in": ([SCHEDULED], WAITING),
        "start": ([WAITING], IN_CONSULTATION),
        "complete": ([WAITING, IN_CONSULTATION], COMPLETED),
        "cancel": ([SCHEDULED, WAITING, IN_CONSULTATION], CANCELLED),
        "reopen": ([COMPLETED], IN_CONSULTATION),
        "restore": ([CANCELLED], None),
    }

    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"
    PRIORITY_CHOICES = [(EMERGENCY, "Emergency"), (URGENT, "Urgent"), (ROUTINE, "Routine")]
    PRIORITY_COLORS = {EMERGENCY: "danger", URGENT: "warning", ROUTINE: "success"}
    PRIORITY_RANK = {EMERGENCY: 0, URGENT: 1, ROUTINE: 2}

    number = models.CharField("appointment no.", max_length=20, unique=True, editable=False)
    branch = models.ForeignKey("branches.Branch", related_name="appointments", on_delete=models.PROTECT)
    priority = models.CharField(
        "triage", max_length=10, choices=PRIORITY_CHOICES, default=ROUTINE, db_index=True,
        help_text="Emergency and urgent cases go to the top of the queue.",
    )
    scheduled_time = models.TimeField(
        "booked time", null=True, blank=True, help_text="For booked visits; walk-ins join the queue by token."
    )
    client = models.ForeignKey("clients.Client", related_name="appointments", on_delete=models.PROTECT, verbose_name="owner")
    pet = models.ForeignKey("clients.Pet", related_name="appointments", on_delete=models.PROTECT)
    visit_date = models.DateField(default=timezone.localdate, db_index=True)
    arrival_time = models.TimeField(null=True, blank=True)
    token = models.PositiveIntegerField(null=True, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=WAITING, db_index=True)
    reason = models.CharField("reason for visit", max_length=255)
    attended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="attended_appointments",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={"is_staff": True},
    )

    weight_kg = models.DecimalField("body weight (kg)", max_digits=6, decimal_places=2, null=True, blank=True)
    clinical_notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    result_notes = models.TextField("result notes", blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    follow_up_of = models.ForeignKey(
        "self", related_name="follow_ups", on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )
    cancellation_reason = models.CharField(max_length=255, blank=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False, related_name="+"
    )

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        ordering = ["-visit_date", "token", "arrival_time", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "visit_date", "token"], condition=Q(token__isnull=False),
                name="appointment_unique_branch_daily_token",
            )
        ]
        permissions = [
            ("view_clinical", "Can view clinical details"),
            ("record_clinical", "Can record clinical details"),
            ("change_completed_appointment", "Can edit completed appointments"),
        ]

    def __str__(self):
        return self.number or "New appointment"

    def get_absolute_url(self):
        return reverse("dashboard:edit", args=["appointments", "appointment", self.pk])

    # Validation

    def clean(self):
        if self.pet_id and self.client_id and self.pet.client_id != self.client_id:
            raise ValidationError({"pet": "This pet belongs to a different owner."})

    # Numbers and tokens

    @property
    def is_locked(self):
        """Completed and cancelled visits are closed to ordinary edits."""
        return self.status in (self.COMPLETED, self.CANCELLED)

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, "secondary")

    def _next_number(self):
        prefix = f"APT-{self.visit_date.year}-"
        last = (
            Appointment.objects.filter(number__startswith=prefix).aggregate(last=Max("number"))["last"]
        )
        sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{sequence:05d}"

    def _next_token(self):
        last = (
            Appointment.objects.filter(branch_id=self.branch_id, visit_date=self.visit_date)
            .aggregate(last=Max("token"))["last"]
        )
        return (last or 0) + 1

    def _needs_token(self):
        return self.token is None and self.status not in (self.SCHEDULED, self.CANCELLED)

    def save(self, *args, **kwargs):
        if self.branch_id is None:
            # Visits made outside the screens (imports, scripts) go to the main branch.
            from apps.branches.models import Branch

            self.branch = Branch.main()
        # Numbers and tokens come from the highest one in use; if two people save at the
        # same moment the database rejects the duplicate and we simply take the next one.
        attempts = 5
        for attempt in range(attempts):
            new_number = not self.number
            new_token = self._needs_token()
            if new_number:
                self.number = self._next_number()
            if new_token:
                self.token = self._next_token()
                if self.arrival_time is None:
                    self.arrival_time = timezone.localtime().time().replace(second=0, microsecond=0)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and (new_number or new_token):
                extra = {"number"} if new_number else set()
                if new_token:
                    extra |= {"token", "arrival_time"}
                kwargs["update_fields"] = {*update_fields, *extra}
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if attempt == attempts - 1:
                    raise
                if new_number:
                    self.number = ""
                if new_token:
                    self.token = None

    # Status changes

    def can_apply(self, action):
        allowed_from, _ = self.TRANSITIONS.get(action, ([], None))
        return self.status in allowed_from

    def apply(self, action, user=None, reason=""):
        """Move the visit to its next status. Callers check permissions first."""
        if not self.can_apply(action):
            raise ValidationError(f"A {self.get_status_display().lower()} appointment cannot be changed that way.")
        now = timezone.now()
        today = timezone.localdate()

        if action == "check_in":
            self.status = self.WAITING
            if self.visit_date != today:
                self.visit_date = today
            self.arrival_time = None
        elif action == "start":
            self.status = self.IN_CONSULTATION
            self.started_at = self.started_at or now
            if self.attended_by_id is None and user is not None and can_attend(user, self.branch):
                self.attended_by = user
        elif action == "complete":
            self.status = self.COMPLETED
            self.started_at = self.started_at or now
            self.completed_at = now
        elif action == "cancel":
            self.status = self.CANCELLED
            self.cancellation_reason = reason[:255]
        elif action == "reopen":
            self.status = self.IN_CONSULTATION
            self.completed_at = None
        elif action == "restore":
            self.cancellation_reason = ""
            self.status = self.WAITING if self.token or self.visit_date <= today else self.SCHEDULED

        if user is not None:
            self.updated_by = user
        self.save()

    # Follow-ups

    @property
    def priority_color(self):
        return self.PRIORITY_COLORS.get(self.priority, "secondary")

    def create_follow_up(self, user):
        existing = self.follow_ups.exclude(status=self.CANCELLED).first()
        if existing:
            return existing, False
        summary = self.diagnosis.strip().splitlines()[0] if self.diagnosis.strip() else self.reason
        attending = self.attended_by if self.attended_by and can_attend(self.attended_by, self.branch) else None
        follow_up = Appointment.objects.create(
            branch=self.branch,
            client=self.client,
            pet=self.pet,
            visit_date=self.follow_up_date,
            status=self.SCHEDULED,
            reason=f"Follow-up: {summary}"[:255],
            attended_by=attending,
            follow_up_of=self,
            created_by=user,
            updated_by=user,
        )
        return follow_up, True


def attending_staff(branch=None):
    """Staff who can be chosen in “Attended by”: those who work at the branch, if one is given."""
    from django.contrib.auth import get_user_model

    queryset = get_user_model().objects.filter(is_active=True, is_staff=True, staff_profile__can_attend=True)
    if branch is not None:
        queryset = queryset.filter(
            Q(is_superuser=True) | Q(staff_profile__all_branches=True) | Q(staff_profile__branches=branch)
        )
    return queryset.distinct().order_by("first_name", "last_name", "username")


def can_attend(user, branch=None):
    return attending_staff(branch).filter(pk=user.pk).exists()


class AppointmentHistory(models.Model):
    appointment = models.ForeignKey(Appointment, related_name="history", on_delete=models.CASCADE)
    option = models.ForeignKey("clinic_setup.HistoryOption", on_delete=models.PROTECT, verbose_name="history")
    value = models.CharField(max_length=255)
    is_abnormal = models.BooleanField("outside normal", default=False, editable=False)

    class Meta:
        ordering = ["option__order", "option__name"]
        verbose_name = "history entry"
        verbose_name_plural = "history"
        constraints = [
            models.UniqueConstraint(fields=["appointment", "option"], name="appointment_history_unique_option")
        ]

    def __str__(self):
        return f"{self.option}: {self.value}"

    @property
    def definition(self):
        return self.option

    def save(self, *args, **kwargs):
        self.is_abnormal = self.option.is_abnormal(self.value)
        super().save(*args, **kwargs)


class ExaminationResult(models.Model):
    appointment = models.ForeignKey(Appointment, related_name="examinations", on_delete=models.CASCADE)
    exam_type = models.ForeignKey("clinic_setup.ExaminationType", on_delete=models.PROTECT, verbose_name="examination")
    value = models.CharField(max_length=60)
    is_abnormal = models.BooleanField("outside normal range", default=False, editable=False)

    class Meta:
        ordering = ["exam_type__order", "exam_type_id"]
        constraints = [
            models.UniqueConstraint(fields=["appointment", "exam_type"], name="examination_result_unique_type")
        ]

    def __str__(self):
        return f"{self.exam_type}: {self.value}{self.exam_type.unit_suffix}"

    @property
    def definition(self):
        return self.exam_type

    def save(self, *args, **kwargs):
        # Worked out from the safe range, never entered by hand.
        self.is_abnormal = self.exam_type.is_abnormal(self.value)
        super().save(*args, **kwargs)


class VaccinationRecord(models.Model):
    appointment = models.ForeignKey(Appointment, related_name="vaccinations", on_delete=models.CASCADE)
    vaccine = models.ForeignKey("clinic_setup.VaccinationType", on_delete=models.PROTECT)
    given_on = models.DateField(
        null=True, blank=True, help_text="When the dose was given. Earlier doses the owner reports can be recorded too."
    )
    batch_number = models.CharField("batch / lot no.", max_length=60, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    reminded_at = models.DateTimeField("owner reminded", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["vaccine__order", "vaccine__name"]
        verbose_name = "vaccination"
        constraints = [
            models.UniqueConstraint(fields=["appointment", "vaccine"], name="vaccination_record_unique_vaccine")
        ]

    def __str__(self):
        return str(self.vaccine)

    def suggest_next_due(self):
        if self.given_on and self.vaccine.booster_interval_days:
            return self.given_on + datetime.timedelta(days=self.vaccine.booster_interval_days)
        return None

    def save(self, *args, **kwargs):
        if self.next_due_date is None:
            self.next_due_date = self.suggest_next_due()
        super().save(*args, **kwargs)
        PlannedVaccination.mark_given(self)


def apply_treatment_template(visit, template):
    """Add a template's lines to the visit's treatment, priced for the visit's branch. Returns how many."""
    count = 0
    for line in template.lines.select_related("item"):
        item = line.item
        price = item.price_at(visit.branch)
        Treatment.objects.create(
            appointment=visit,
            item=item,
            kind=Treatment.KIND_FROM_CATALOGUE.get(item.treatment_kind, "medication"),
            name=item.name,
            dose=line.dose or item.default_dose,
            route=line.route or item.default_route,
            frequency=line.frequency or item.default_frequency,
            duration=line.duration or item.default_duration,
            notes=line.notes,
            quantity=line.quantity,
            unit_price=price if price else None,
        )
        count += 1
    if template.diagnosis and not visit.diagnosis.strip():
        visit.diagnosis = template.diagnosis
        visit.save(update_fields=["diagnosis"])
    return count


class PlannedVaccination(models.Model):
    """A dose a pet is due for under a vaccination plan. It is ticked off when the vaccine is recorded."""

    DUE = "due"
    GIVEN = "given"
    SKIPPED = "skipped"
    STATUS_CHOICES = [(DUE, "Due"), (GIVEN, "Given"), (SKIPPED, "Skipped")]

    pet = models.ForeignKey("clients.Pet", related_name="planned_vaccinations", on_delete=models.CASCADE)
    plan = models.ForeignKey("clinic_setup.VaccinationPlan", related_name="+", on_delete=models.PROTECT)
    vaccine = models.ForeignKey("clinic_setup.VaccinationType", related_name="+", on_delete=models.PROTECT)
    label = models.CharField(max_length=60, blank=True)
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DUE)
    record = models.ForeignKey(
        VaccinationRecord, related_name="+", on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )
    reminded_at = models.DateTimeField("owner reminded", null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]
        verbose_name = "planned vaccination"

    def __str__(self):
        return f"{self.vaccine}{f' ({self.label})' if self.label else ''} due {self.due_date:%d %b %Y}"

    @property
    def is_overdue(self):
        return self.status == self.DUE and self.due_date < timezone.localdate()

    @property
    def title(self):
        return f"{self.vaccine}{f' ({self.label})' if self.label else ''}"

    @classmethod
    def enrol(cls, pet, plan, start, user=None):
        """Put the pet on the plan from the start date. Doses already planned for this plan are replaced."""
        cls.objects.filter(pet=pet, plan=plan, status=cls.DUE).delete()
        return cls.objects.bulk_create([
            cls(
                pet=pet, plan=plan, vaccine_id=dose.vaccine_id, label=dose.label, created_by=user,
                due_date=start + datetime.timedelta(days=dose.days_after_start),
            )
            for dose in plan.doses.all()
        ])

    @classmethod
    def mark_given(cls, record):
        """A recorded dose ticks off the earliest planned dose of the same vaccine."""
        if record.appointment.status == Appointment.CANCELLED:
            return
        planned = (
            cls.objects.filter(pet_id=record.appointment.pet_id, vaccine_id=record.vaccine_id, status=cls.DUE)
            .order_by("due_date")
            .first()
        )
        if planned is not None and not cls.objects.filter(record=record).exists():
            planned.status, planned.record = cls.GIVEN, record
            planned.save(update_fields=["status", "record"])


def due_vaccinations(start, end, branch_ids=None):
    """The latest dose of each vaccine per pet, where the next dose falls between start and end."""
    later_dose = VaccinationRecord.objects.filter(
        appointment__pet=OuterRef("appointment__pet"),
        vaccine=OuterRef("vaccine"),
        appointment__visit_date__gt=OuterRef("appointment__visit_date"),
    ).exclude(appointment__status=Appointment.CANCELLED)
    records = VaccinationRecord.objects.all()
    if branch_ids is not None:
        records = records.filter(appointment__branch_id__in=branch_ids)
    return (
        records.filter(next_due_date__range=(start, end))
        .exclude(appointment__status=Appointment.CANCELLED)
        .exclude(appointment__pet__is_deceased=True)
        .annotate(has_later_dose=Exists(later_dose))
        .filter(has_later_dose=False)
        .select_related("vaccine", "appointment__pet__species", "appointment__client")
        .order_by("next_due_date")
    )


class Treatment(models.Model):
    KIND_CHOICES = [
        ("medication", "Medication"),
        ("procedure", "Procedure"),
        ("advice", "Advice"),
    ]

    appointment = models.ForeignKey(Appointment, related_name="treatments", on_delete=models.CASCADE)
    item = models.ForeignKey(
        "shop.Product",
        related_name="treatments",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="catalogue item",
        help_text="Pick from the treatment catalogue to fill in the details and price.",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="medication")
    name = models.CharField("medicine / procedure", max_length=150)
    dose = models.CharField(max_length=60, blank=True)
    route = models.CharField(max_length=60, blank=True, help_text="e.g. oral, SC, IM, IV")
    frequency = models.CharField(max_length=60, blank=True, help_text="e.g. twice a day")
    duration = models.CharField(max_length=60, blank=True, help_text="e.g. 5 days")
    notes = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField("qty to bill", max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(
        "price", max_digits=10, decimal_places=2, null=True, blank=True, help_text="Leave blank for no charge."
    )

    # Catalogue kinds map onto the kinds used here.
    KIND_FROM_CATALOGUE = {"medicine": "medication", "procedure": "procedure", "advice": "advice"}

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name

    @property
    def amount(self):
        if self.unit_price is None:
            return None
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @property
    def is_billable(self):
        return bool(self.unit_price) and self.quantity > 0

    def bill_description(self):
        details = " · ".join(part for part in [self.dose, self.route, self.frequency, self.duration] if part)
        return f"{self.name} ({details})"[:200] if details else self.name
