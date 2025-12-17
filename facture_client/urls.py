from django.urls import path

from .views import (
    FactureClientListCreateView,
    FactureClientDetailEditDeleteView,
    GenerateNumeroFactureView,
    FactureClientStatusUpdateView,
)

app_name = "facture_client"

urlpatterns = [
    # GET Facture pro forma list (paginated) & POST create
    path(
        "",
        FactureClientListCreateView.as_view(),
        name="facture-client-list-create",
    ),
    # GET facture-client detail, PUT update, DELETE
    path(
        "<int:pk>/",
        FactureClientDetailEditDeleteView.as_view(),
        name="facture-client-detail",
    ),
    # GET generated numero facture-client
    path(
        "generate_num_facture_client/",
        GenerateNumeroFactureView.as_view(),
        name="generate-numero-facture-client",
    ),
    # PATCH : switch status of facture-client
    path(
        "switch_statut/<int:pk>/",
        FactureClientStatusUpdateView.as_view(),
        name="facture-client-statut-update",
    ),
]
