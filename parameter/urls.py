from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    VilleViewSet,
    MarqueViewSet,
    CategorieViewSet,
    UniteViewSet,
    EmplacementViewSet,
)

app_name = "parameter"

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r"ville", VilleViewSet, basename="ville")
router.register(r"marque", MarqueViewSet, basename="marque")
router.register(r"categorie", CategorieViewSet, basename="categorie")
router.register(r"unite", UniteViewSet, basename="unite")
router.register(r"emplacement", EmplacementViewSet, basename="emplacement")

urlpatterns = [
    path("", include(router.urls)),
]
