from django.urls import path

from .views import (
    FactureProFormaListCreateView,
    FactureProFormaDetailEditDeleteView,
    GenerateNumeroFactureView,
    FactureProFormaStatusUpdateView,
    FactureProFormaConvertToFactureClientView,
    FactureProFormaPDFView,
)

app_name = "facture_proforma"

urlpatterns = [
    # GET Facture pro forma list (paginated) & POST create
    path(
        "",
        FactureProFormaListCreateView.as_view(),
        name="facture-proforma-list-create",
    ),
    # GET facture-proforma detail, PUT update, DELETE
    path(
        "<int:pk>/",
        FactureProFormaDetailEditDeleteView.as_view(),
        name="facture-proforma-detail",
    ),
    # GET generated numero facture-proforma
    path(
        "generate_num_facture_proforma/",
        GenerateNumeroFactureView.as_view(),
        name="generate-numero-facture-proforma",
    ),
    # PATCH : switch status of facture-proforma
    path(
        "switch_statut/<int:pk>/",
        FactureProFormaStatusUpdateView.as_view(),
        name="facture-proforma-statut-update",
    ),
    # POST : convert facture-porforma to facture client
    path(
        "convert_to_facture_client/<int:pk>/",
        FactureProFormaConvertToFactureClientView.as_view(),
        name="convert-to-facture-client",
    ),
    # GET : generate PDF
    path(
        "pdf/fr/<int:pk>/", FactureProFormaPDFView.as_view(), {"language": "fr"}, name="facture-proforma-pdf-fr"
    ),
    path(
        "pdf/en/<int:pk>/", FactureProFormaPDFView.as_view(), {"language": "en"}, name="facture-proforma-pdf-en"
    ),
]
