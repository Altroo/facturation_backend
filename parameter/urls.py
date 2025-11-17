from django.urls import path

from .views import (
    VilleListCreateView,
    VilleDetailEditDeleteView,
)

app_name = "parameter"

urlpatterns = [
    # GET ville list & POST create
    path("ville/", VilleListCreateView.as_view()),
    # GET ville detail, PUT update, DELETE
    path("ville/<int:pk>/", VilleDetailEditDeleteView.as_view()),
]
