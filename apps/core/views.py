from django.views.generic import TemplateView

from apps.contact.forms import ContactForm
from apps.faq.models import FAQ
from apps.services.models import Service
from apps.team.models import TeamMember
from apps.testimonials.models import Testimonial

from .models import HeroSlide, Stat


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            slides=HeroSlide.objects.active(),
            services=Service.objects.active().filter(is_featured=True)[:6],
            stats=Stat.objects.active(),
            testimonials=Testimonial.objects.active(),
            team=TeamMember.objects.active()[:3],
            form=ContactForm(),
        )
        return context


class AboutView(TemplateView):
    template_name = "core/about.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            stats=Stat.objects.active(),
            faqs=FAQ.objects.active()[:3],
        )
        return context
