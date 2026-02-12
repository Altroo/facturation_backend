"""
URL configuration for Facturation project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    """Simple health check endpoint for Docker/load balancer health checks."""
    return JsonResponse({"status": "healthy"})


urlpatterns = [
    # Health check endpoint (unauthenticated)
    path("api/health/", health_check, name="health-check"),
    # Account
    path("api/account/", include("account.urls")),
    # Company
    path("api/company/", include("company.urls")),
    # Client
    path("api/client/", include("client.urls")),
    # Article
    path("api/article/", include("article.urls")),
    # Devi
    path("api/devi/", include("devi.urls")),
    # Facture Proforma
    path("api/facture_proforma/", include("facture_proforma.urls")),
    # Facture Client
    path("api/facture_client/", include("facture_client.urls")),
    # Bon de Livraison
    path("api/bon_de_livraison/", include("bon_de_livraison.urls")),
    # Reglement
    path("api/reglement/", include("reglement.urls")),
    # Parameter
    path("api/parameter/", include("parameter.urls")),
    # Dashboard
    path("api/dashboard/", include("dashboard.urls")),
    # Admin panel
    path("admin/", admin.site.urls),
]

# Serve static and media files in development
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
