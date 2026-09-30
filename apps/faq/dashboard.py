from apps.dashboard.registry import Module, site

from .models import FAQ, FAQCategory


@site.register(FAQCategory)
class FAQCategoryModule(Module):
    icon = "ki-category"
    description = "The headings that questions are grouped under."
    list_display = ["name", "question_count", "order", "is_active"]
    search_fields = ["name"]
    toggle_fields = ["is_active"]

    def question_count(self, obj):
        return obj.faqs.count()

    question_count.short_description = "Questions"


@site.register(FAQ)
class FAQModule(Module):
    icon = "ki-question-2"
    description = "Questions and answers."
    list_display = ["question", "category", "service", "order", "is_active"]
    search_fields = ["question", "answer"]
    list_filter = ["category", "service", "is_active"]
    toggle_fields = ["is_active"]
