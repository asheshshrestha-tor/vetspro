from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    # Honeypot: hidden from people, so only bots fill it in.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "branch", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Name", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone (optional)", "autocomplete": "tel"}),
            "message": forms.Textarea(attrs={"placeholder": "Message", "rows": 5}),
        }

    branch = forms.ModelChoiceField(queryset=None, required=False, empty_label="Any branch", label="Branch")

    field_order = ["name", "email", "phone", "branch", "message"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.branches.models import Branch

        branches = Branch.objects.filter(is_active=True)
        if branches.count() > 1:
            self.fields["branch"].queryset = branches
        else:
            del self.fields["branch"]

    @property
    def is_spam(self):
        return bool(self.cleaned_data.get("website"))
