from apps.dashboard.forms import DashboardModelForm
from apps.dashboard.registry import Module, site

from .models import ExaminationType, HistoryOption, Species, ValueDefinition, VaccinationType

DEFINITION_FIELDS = [
    "name", "value_kind", "unit", "min_value", "max_value", "options", "normal_options", "description", "order",
    "is_active",
]

# Which settings apply to which value type; the form hides the rest.
SHOW_FOR = {
    "unit": [ValueDefinition.NUMBER],
    "min_value": [ValueDefinition.NUMBER],
    "max_value": [ValueDefinition.NUMBER],
    "options": [ValueDefinition.CHOICE],
    "normal_options": [ValueDefinition.CHOICE, ValueDefinition.YES_NO],
}


class DefinitionForm(DashboardModelForm):
    """A visit field: its name, how its value is entered, and what counts as normal."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, kinds in SHOW_FOR.items():
            if name in self.fields:
                self.fields[name].widget.attrs["data-show-for-kind"] = " ".join(kinds)
        kind = self.fields.get("value_kind")
        if kind is not None:
            kind.help_text = "Changes which settings below apply."
            if self.in_use():
                # Stored values were entered for this type; changing it would make them meaningless.
                kind.disabled = True
                kind.help_text = "Locked because visits already have values for this field."

    def in_use(self):
        if not self.instance.pk:
            return False
        for relation in self.instance._meta.related_objects:
            accessor = relation.get_accessor_name()
            if getattr(self.instance, accessor).exists():
                return True
        return False

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("value_kind")
        low, high = cleaned.get("min_value"), cleaned.get("max_value")
        if kind == ValueDefinition.NUMBER and low is not None and high is not None and low > high:
            self.add_error("max_value", "The upper limit must not be below the lower limit.")
        if kind == ValueDefinition.CHOICE:
            options = [line.strip() for line in cleaned.get("options", "").splitlines() if line.strip()]
            if not options:
                self.add_error("options", "Enter at least one option, one per line.")
            allowed = {option.lower() for option in options}
        elif kind == ValueDefinition.YES_NO:
            allowed = {"yes", "no"}
        else:
            allowed = None
        if allowed is not None:
            normal = [line.strip() for line in cleaned.get("normal_options", "").splitlines() if line.strip()]
            unknown = [value for value in normal if value.lower() not in allowed]
            if unknown:
                self.add_error("normal_options", f"Not one of the options: {', '.join(unknown)}.")
        return cleaned


class LookupModule(Module):
    group = "Clinic setup"
    show_on_home = False
    list_display = ["name", "description", "order", "is_active"]
    search_fields = ["name", "description"]
    list_filter = ["is_active"]
    toggle_fields = ["is_active"]


class DefinitionModule(LookupModule):
    list_display = ["name", "kind", "normal", "order", "is_active"]
    form_class = DefinitionForm
    fields = DEFINITION_FIELDS

    def kind(self, obj):
        return obj.get_value_kind_display()

    kind.short_description = "Value type"

    def normal(self, obj):
        return obj.range_label

    normal.short_description = "Normal"


@site.register(Species)
class SpeciesModule(LookupModule):
    icon = "ki-abstract-26"
    description = "Kinds of animal, e.g. dog, cat, rabbit."
    menu_order = 10


@site.register(HistoryOption)
class HistoryOptionModule(DefinitionModule):
    icon = "ki-notepad-edit"
    description = (
        "The Patient's History section of every visit. Each field here appears on the visit form "
        "and staff fill in its value."
    )
    menu_order = 20


@site.register(ExaminationType)
class ExaminationTypeModule(DefinitionModule):
    icon = "ki-pulse"
    description = (
        "The Clinical Examination section of every visit. Values outside the normal range or "
        "normal options are flagged. A field that visits already use cannot be deleted; untick “in use” instead."
    )
    menu_order = 30


@site.register(VaccinationType)
class VaccinationTypeModule(LookupModule):
    icon = "ki-shield-tick"
    description = (
        "The Vaccination Record section of every visit. The booster interval suggests the next due date."
    )
    menu_order = 40
    list_display = ["name", "booster_interval_days", "order", "is_active"]
    fields = ["name", "booster_interval_days", "description", "order", "is_active"]
