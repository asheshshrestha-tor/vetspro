from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from apps.core.sitemaps import sitemaps

admin.site.site_header = "BMB Veterinary Hospital"
admin.site.site_title = "BMB Vets admin"
admin.site.index_title = "Website content"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
    path("services/", include("apps.services.urls")),
    path("team/", include("apps.team.urls")),
    path("pricing/", include("apps.pricing.urls")),
    path("faq/", include("apps.faq.urls")),
    path("gallery/", include("apps.gallery.urls")),
    path("contact/", include("apps.contact.urls")),
    path("shop/", include("apps.shop.urls")),
    path("branches/", include("apps.branches.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
