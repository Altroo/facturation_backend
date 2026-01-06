from django.urls import path

from .views import (
    ReglementListCreateView,
    ReglementDetailEditDeleteView,
    ReglementStatusUpdateView,
    ReglementPDFView,
)

app_name = "reglement"

urlpatterns = [
    # GET règlement list (paginated) & POST create règlement
    path(
        "",
        ReglementListCreateView.as_view(),
        name="reglement-list-create",
    ),
    # GET règlement detail, PUT update, DELETE
    path(
        "<int:pk>/",
        ReglementDetailEditDeleteView.as_view(),
        name="reglement-detail",
    ),
    # PATCH: switch status of règlement
    path(
        "switch_statut/<int:pk>/",
        ReglementStatusUpdateView.as_view(),
        name="reglement-statut-update",
    ),
    # GET : generate PDF receipt
    path("pdf/<int:pk>/", ReglementPDFView.as_view(), name="reglement-pdf"),
]
