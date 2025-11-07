from django.urls import path

from .views import (
    CompanyListCreateView,
    CompanyDetailView,
)

app_name = "company"

urlpatterns = [
    # GET list (paginated) & POST create
    path("", CompanyListCreateView.as_view()),
    # GET detail, PUT update, DELETE
    path("<int:pk>/", CompanyDetailView.as_view()),
]
