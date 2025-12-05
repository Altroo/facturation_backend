from django.urls import path

from .views import (
    DeviListCreateView,
    DeviDetailEditDeleteView,
    GenerateNumeroDevisView,
    DeviStatusUpdateView,
    DeviLineDetailEditDeleteView,
    DeviLineListCreateView,
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
    # GET Devi line list (paginated) & POST create
    path("lines/", DeviLineListCreateView.as_view(), name="devi-line-list-create"),
    # GET Devi line detail, PUT update, DELETE
    path(
        "lines/<int:pk>/",
        DeviLineDetailEditDeleteView.as_view(),
        name="devi-line-detail-edit-delete",
    ),
]
