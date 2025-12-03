from django.urls import path

from .views import (
    DeviListCreateView,
    DeviDetailEditDeleteView,
    GenerateNumeroDevisView,
    DeviStatusUpdateView,
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
        "<int:pk>/switch_status/",
        DeviStatusUpdateView.as_view(),
        name="devi-status-update",
    ),
]
