from django.urls import path

from .views import (
    CompanyListCreateView,
    CompanyDetailView,
)

app_name = "company"

urlpatterns = [
    # GET company list (paginated) & POST create
    path("", CompanyListCreateView.as_view()),
    # GET company detail, PUT update, DELETE
    path("<int:pk>/", CompanyDetailView.as_view()),
]
