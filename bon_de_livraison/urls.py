from django.urls import path

from .views import (
    BonDeLivraisonListCreateView,
    BonDeLivraisonDetailEditDeleteView,
    GenerateNumeroBonDeLivraisonView,
    BonDeLivraisonStatusUpdateView,
    BonDeLivraisonUninvoicedListView,
    BonDeLivraisonPDFView,
)

app_name = "bon_de_livraison"

urlpatterns = [
    # GET BonDeLivraison list (paginated) & POST create
    path(
        "", BonDeLivraisonListCreateView.as_view(), name="bon-de-livraison-list-create"
    ),
    # GET uninvoiced BonDeLivraison list (read-only)
    path(
        "uninvoiced/",
        BonDeLivraisonUninvoicedListView.as_view(),
        name="bon-de-livraison-uninvoiced-list",
    ),
    # GET BonDeLivraison detail, PUT update, DELETE
    path(
        "<int:pk>/",
        BonDeLivraisonDetailEditDeleteView.as_view(),
        name="bon-de-livraison-detail",
    ),
    # GET generated numero bon de livraison
    path(
        "generate_num_bon_livraison/",
        GenerateNumeroBonDeLivraisonView.as_view(),
        name="generate-numero-bon-livraison",
    ),
    # PATCH : switch status of bon de livraison
    path(
        "switch_statut/<int:pk>/",
        BonDeLivraisonStatusUpdateView.as_view(),
        name="bon-de-livraison-statut-update",
    ),
    # GET : generate PDF
    path("pdf/fr/<int:pk>/", BonDeLivraisonPDFView.as_view(), {"language": "fr"}, name="bon-de-livraison-pdf-fr"),
    path("pdf/en/<int:pk>/", BonDeLivraisonPDFView.as_view(), {"language": "en"}, name="bon-de-livraison-pdf-en"),
]
