from django.views.generic import DetailView, ListView

from .models import TeamMember


class TeamListView(ListView):
    template_name = "team/team_list.html"
    context_object_name = "team"

    def get_queryset(self):
        return TeamMember.objects.active()


class TeamDetailView(DetailView):
    template_name = "team/team_detail.html"
    context_object_name = "member"

    def get_queryset(self):
        return TeamMember.objects.active().prefetch_related("experiences")
