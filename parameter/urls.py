from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    VilleViewSet,
    MarqueViewSet,
    CategorieViewSet,
    UniteViewSet,
    EmplacementViewSet,
    ModePaiementViewSet,
    ModeReglementViewSet,
    LivreParViewSet,
)

app_name = "parameter"

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r"ville", VilleViewSet, basename="ville")
router.register(r"marque", MarqueViewSet, basename="marque")
router.register(r"categorie", CategorieViewSet, basename="categorie")
router.register(r"unite", UniteViewSet, basename="unite")
router.register(r"emplacement", EmplacementViewSet, basename="emplacement")
router.register(r"mode_paiement", ModePaiementViewSet, basename="mode_paiement")
router.register(r"mode_reglement", ModeReglementViewSet, basename="mode_reglement")
router.register(r"livre_par", LivreParViewSet, basename="livre_par")

urlpatterns = [
    path("", include(router.urls)),
]
