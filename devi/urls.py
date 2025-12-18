from django.urls import path

from .views import (
    DeviListCreateView,
    DeviDetailEditDeleteView,
    GenerateNumeroDevisView,
    DeviStatusUpdateView,
    DeviConvertToFactureProformaView,
    DeviConvertToFactureClientView,
)

app_name = "devi"

urlpatterns = [
    # GET Devi list (paginated) & POST create
    path("", DeviListCreateView.as_view(), name="devi-list-create"),
    # GET Devi detail, PUT update, DELETE
    path("<int:pk>/", DeviDetailEditDeleteView.as_view(), name="devi-detail"),
    # GET generated numero devis
    path(
        "generate_num_devis/",
        GenerateNumeroDevisView.as_view(),
        name="generate-numero-devis",
    ),
    # PATCH : switch status of devi
    path(
        "switch_statut/<int:pk>/",
        DeviStatusUpdateView.as_view(),
        name="devi-statut-update",
    ),
    # POST : convert devi to facture pro-forma
    path(
        "convert_to_facture_proforma/<int:pk>/",
        DeviConvertToFactureProformaView.as_view(),
        name="convert-to-facture-proforma",
    ),
    # POST : convert devi to facture client
    path(
        "convert_to_facture_client/<int:pk>/",
        DeviConvertToFactureClientView.as_view(),
        name="convert-to-facture-client",
    ),
]
