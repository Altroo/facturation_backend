from django.urls import path

from .views import (
    FactureClientListCreateView,
    FactureClientDetailEditDeleteView,
    GenerateNumeroFactureView,
    FactureClientStatusUpdateView,
    FactureClientConvertToBonDeLivraisonView,
    FactureClientUnpaidListView,
    FactureClientForPaymentView,
    FactureClientPDFView,
)

app_name = "facture_client"

urlpatterns = [
    # GET Facture pro forma list (paginated) & POST create
    path(
        "",
        FactureClientListCreateView.as_view(),
        name="facture-client-list-create",
    ),
    # GET unpaid factures list (read-only)
    path(
        "unpaid/",
        FactureClientUnpaidListView.as_view(),
        name="facture-client-unpaid-list",
    ),
    # GET factures available for payment (for reglement form)
    path(
        "for_payment/",
        FactureClientForPaymentView.as_view(),
        name="facture-client-for-payment",
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
    # POST : convert facture client to bon de livraison
    path(
        "convert_to_bon_de_livraison/<int:pk>/",
        FactureClientConvertToBonDeLivraisonView.as_view(),
        name="convert-to-bon-de-livraison",
    ),
    # GET : generate PDF
    path("pdf/<int:pk>/", FactureClientPDFView.as_view(), name="facture-client-pdf"),
]
