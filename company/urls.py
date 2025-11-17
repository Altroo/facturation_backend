from django.urls import path

from .views import (
    CompanyListCreateView,
    CompanyDetailEditDeleteView,
)

app_name = "company"

urlpatterns = [
    # GET company list (paginated) & POST create
    path("", CompanyListCreateView.as_view(), name="company-list-create"),
    # GET company detail, PUT update, DELETE
    path("<int:pk>/", CompanyDetailEditDeleteView.as_view(), name="company-detail"),
]
