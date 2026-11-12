from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    IncotermViewSet,
    OrigineMarchandiseViewSet,
    NatureMarchandiseViewSet,
    VilleViewSet,
    MarqueViewSet,
    CategorieViewSet,
    UniteViewSet,
    EmplacementViewSet,
    ModePaiementViewSet,
    LivreParViewSet,
)

app_name = "parameter"

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r"incoterm", IncotermViewSet, basename="incoterm")
router.register(r"origine_marchandise", OrigineMarchandiseViewSet, basename="origine_marchandise")
router.register(r"nature_marchandise", NatureMarchandiseViewSet, basename="nature_marchandise")
router.register(r"ville", VilleViewSet, basename="ville")
router.register(r"marque", MarqueViewSet, basename="marque")
router.register(r"categorie", CategorieViewSet, basename="categorie")
router.register(r"unite", UniteViewSet, basename="unite")
router.register(r"emplacement", EmplacementViewSet, basename="emplacement")
router.register(r"mode_paiement", ModePaiementViewSet, basename="mode_paiement")
router.register(r"livre_par", LivreParViewSet, basename="livre_par")

urlpatterns = [
    path("", include(router.urls)),
]
