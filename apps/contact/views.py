import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import ContactForm

logger = logging.getLogger(__name__)


class ContactView(FormView):
    template_name = "contact/contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("contact:contact")

    def get_initial(self):
        initial = super().get_initial()
        branch = self.request.GET.get("branch", "")
        if branch.isdigit():
            initial["branch"] = int(branch)
        return initial

    def form_valid(self, form):
        # Bots get the same success response, but nothing is stored.
        if not form.is_spam:
            message = form.save()
            self.notify(message)
        messages.success(self.request, "Thank you. Your message has been sent and we will get back to you soon.")
        return super().form_valid(form)

    def notify(self, message):
        if not settings.CONTACT_NOTIFY_EMAIL:
            return
        try:
            send_mail(
                subject=f"Website message from {message.name}",
                message=(
                    f"From: {message.name} <{message.email}>\nPhone: {message.phone}\n"
                    + (f"Branch: {message.branch}\n" if message.branch_id else "")
                    + f"\n{message.message}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_NOTIFY_EMAIL],
            )
        except Exception:
            # The message is already saved; a mail failure must not lose the enquiry.
            logger.exception("Could not send contact notification email")
