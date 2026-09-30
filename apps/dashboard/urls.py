from django.urls import include, path

from . import views
from .registry import site

app_name = "dashboard"

module = "<str:app_label>/<str:model_name>/"

# Pages a module adds for itself come first, so they are matched before the generic ones.
module_pages = [
    path(f"{m.app_label}/{m.model_name}/", include(m.get_urls()))
    for m in site.modules()
    if m.get_urls()
]

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("password/", views.PasswordChangeView.as_view(), name="password"),
    *module_pages,
    path(module, views.module_view("list", views.ModuleListView), name="list"),
    path(module + "add/", views.module_view("add", views.ModuleFormView), name="add"),
    path(module + "autocomplete/", views.AutocompleteView.as_view(), name="autocomplete"),
    path(module + "<int:pk>/", views.module_view("edit", views.ModuleFormView), name="edit"),
    path(module + "<int:pk>/delete/", views.ModuleDeleteView.as_view(), name="delete"),
    path(module + "<int:pk>/toggle/<str:field>/", views.ModuleToggleView.as_view(), name="toggle"),
]
