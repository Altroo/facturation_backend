from django.urls import path

from .views import (
    FactureAvoirListCreateView,
    FactureAvoirDetailEditView,
    GenerateNumeroFactureAvoirView,
    FactureAvoirStatusUpdateView,
    FactureAvoirFromFactureView,
    FactureAvoirPDFView,
)

app_name = "facture_avoir"

urlpatterns = [
    path("", FactureAvoirListCreateView.as_view(), name="facture-avoir-list-create"),
    path(
        "from_facture/<int:pk>/",
        FactureAvoirFromFactureView.as_view(),
        name="facture-avoir-from-facture",
    ),
    path(
        "generate_num_facture_avoir/",
        GenerateNumeroFactureAvoirView.as_view(),
        name="generate-numero-facture-avoir",
    ),
    path(
        "switch_statut/<int:pk>/",
        FactureAvoirStatusUpdateView.as_view(),
        name="facture-avoir-statut-update",
    ),
    path(
        "pdf/fr/<int:pk>/",
        FactureAvoirPDFView.as_view(),
        {"language": "fr"},
        name="facture-avoir-pdf-fr",
    ),
    path(
        "pdf/en/<int:pk>/",
        FactureAvoirPDFView.as_view(),
        {"language": "en"},
        name="facture-avoir-pdf-en",
    ),
    path("<int:pk>/", FactureAvoirDetailEditView.as_view(), name="facture-avoir-detail"),
]
