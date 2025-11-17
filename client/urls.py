from django.urls import path

from .views import (
    ClientListCreateView,
    ClientDetailEditDeleteView,
    GenerateClientCodeView,
    ArchiveToggleClientView,
)

app_name = "client"

urlpatterns = [
    # GET Client list (paginated) & POST create
    path("", ClientListCreateView.as_view()),
    # GET Client detail, PUT update, DELETE
    path("<int:pk>/", ClientDetailEditDeleteView.as_view()),
    # GET generated code client
    path("generate_code_client/", GenerateClientCodeView.as_view()),
    # POST archiver le client
    path("archive/<int:pk>/", ArchiveToggleClientView.as_view()),
]
