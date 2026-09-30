from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="list"),
    path("category/<slug:slug>/", views.ProductListView.as_view(), name="category"),
    path("<slug:slug>/", views.ProductDetailView.as_view(), name="product"),
]
