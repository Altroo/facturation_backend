from django.urls import path

from .views import (
    CompanyListCreateView,
    CompanyDetailEditDeleteView,
    CompaniesByUserView,
)

app_name = "company"

urlpatterns = [
    # GET company list (paginated) & POST create
    path("", CompanyListCreateView.as_view(), name="company-list-create"),
    # GET company detail, PUT update, DELETE
    path("<int:pk>/", CompanyDetailEditDeleteView.as_view(), name="company-detail"),
    # GET companies by user
    path("by_user/", CompaniesByUserView.as_view(), name="company-by-user"),
]
