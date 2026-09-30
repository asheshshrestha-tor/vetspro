from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import models
from django.forms import inlineformset_factory, modelform_factory

INPUT_CLASS = "form-control form-control-solid"
SELECT_CLASS = "form-select form-select-solid"
CHECKBOX_CLASS = "form-check-input"


class ImageInput(forms.ClearableFileInput):
    template_name = "dashboard/widgets/image_input.html"


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


class TimeInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")


class AutocompleteSelect(forms.Select):
    """A dropdown that searches the server as you type, so it never loads the whole table.

    ``forward`` names other fields on the form whose values are sent with each search,
    e.g. the chosen client when picking a pet.
    """

    def __init__(self, url, forward=(), placeholder="Type to search", attrs=None):
        super().__init__(attrs)
        self.url = url
        self.forward = forward
        self.placeholder = placeholder

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs.update(
            {
                "data-autocomplete-url": str(self.url),
                "data-placeholder": self.placeholder,
                "data-forward": ",".join(self.forward),
            }
        )
        return attrs

    def optgroups(self, name, value, attrs=None):
        # Render only the selected option; the rest arrive from the server while typing.
        selected = {str(v) for v in value if v not in (None, "")}
        groups = [(None, [self.create_option(name, "", "", not selected, 0)], 0)]
        queryset = getattr(self.choices, "queryset", None)
        if selected and queryset is not None:
            for index, obj in enumerate(queryset.filter(pk__in=selected), start=1):
                label = self.choices.field.label_from_instance(obj)
                groups.append((None, [self.create_option(name, str(obj.pk), label, True, index)], index))
        return groups


def style_fields(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css = CHECKBOX_CLASS
        elif isinstance(widget, forms.CheckboxSelectMultiple):
            continue
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            css = SELECT_CLASS
        else:
            css = INPUT_CLASS
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()
        if isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("rows", 4)


class DashboardFormMixin:
    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        style_fields(self)


class DashboardForm(DashboardFormMixin, forms.Form):
    pass


class DashboardModelForm(DashboardFormMixin, forms.ModelForm):
    pass


def formfield_callback(db_field, **kwargs):
    if isinstance(db_field, models.ImageField):
        kwargs["widget"] = ImageInput
    elif isinstance(db_field, models.DateField) and not isinstance(db_field, models.DateTimeField):
        kwargs["widget"] = DateInput
    elif isinstance(db_field, models.TimeField):
        kwargs["widget"] = TimeInput
    return db_field.formfield(**kwargs)


def autocomplete_widget(model_field, forward=()):
    from .registry import site

    related = site.for_model(model_field.related_model)
    if related is None:
        return None
    return AutocompleteSelect(related.autocomplete_url, forward=forward)


def build_form(module):
    def callback(db_field, **kwargs):
        if db_field.name in module.autocomplete_fields:
            widget = autocomplete_widget(db_field)
            if widget is not None:
                kwargs["widget"] = widget
        return formfield_callback(db_field, **kwargs)

    return modelform_factory(
        module.model,
        form=module.form_class or DashboardModelForm,
        fields=module.get_fields(),
        formfield_callback=callback,
    )


def build_inline_formsets(module, instance, data=None, files=None):
    formsets = []
    for index, inline_class in enumerate(module.inlines):
        inline = inline_class()
        factory = inlineformset_factory(
            module.model,
            inline.model,
            form=inline.form_class or DashboardModelForm,
            fields=inline.fields,
            formfield_callback=formfield_callback,
            extra=inline.extra,
            can_delete=True,
        )
        formset = factory(data, files, instance=instance, prefix=f"inline{index}")
        formset.title = inline.get_title()
        formsets.append(formset)
    return formsets


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "not_staff": "This account does not have access to the dashboard.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-control bg-transparent", "placeholder": "Username"})
        self.fields["password"].widget.attrs.update({"class": "form-control bg-transparent", "placeholder": "Password"})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(self.error_messages["not_staff"], code="not_staff")


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
