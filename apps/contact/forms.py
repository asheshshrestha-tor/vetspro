from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    # Honeypot: hidden from people, so only bots fill it in.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Name", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone (optional)", "autocomplete": "tel"}),
            "message": forms.Textarea(attrs={"placeholder": "Message", "rows": 5}),
        }

    @property
    def is_spam(self):
        return bool(self.cleaned_data.get("website"))
