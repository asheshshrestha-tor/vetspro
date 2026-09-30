from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.services.models import Service
from apps.team.models import TeamMember


class StaticSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return [
            "core:home",
            "core:about",
            "services:list",
            "pricing:list",
            "team:list",
            "faq:list",
            "gallery:list",
            "contact:contact",
            "shop:list",
        ]

    def location(self, item):
        return reverse(item)


class ServiceSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return Service.objects.active()

    def lastmod(self, obj):
        return obj.updated_at


class TeamSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return TeamMember.objects.active()

    def lastmod(self, obj):
        return obj.updated_at


class ProductSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        from apps.shop.models import Product

        return Product.objects.online()

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {"static": StaticSitemap, "services": ServiceSitemap, "team": TeamSitemap, "products": ProductSitemap}
