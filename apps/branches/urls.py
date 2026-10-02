from django.urls import path

from . import views

app_name = "branches"

urlpatterns = [path("", views.BranchListView.as_view(), name="list")]
