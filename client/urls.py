from django.urls import path

from .views import (
    ClientListCreateView,
    ClientDetailEditDeleteView,
    ClientHistoryView,
    ClientStatementPDFView,
    GenerateClientCodeView,
    ArchiveToggleClientView,
    BulkDeleteClientView,
    BulkArchiveClientView,
)

app_name = "client"

urlpatterns = [
    # GET Client list (paginated) & POST create
    path("", ClientListCreateView.as_view(), name="client-list-create"),
    # DELETE bulk delete clients
    path("bulk_delete/", BulkDeleteClientView.as_view(), name="client-bulk-delete"),
    # PATCH bulk archive/unarchive clients
    path("bulk_archive/", BulkArchiveClientView.as_view(), name="client-bulk-archive"),
    # GET full client document/payment history
    path("<int:pk>/history/", ClientHistoryView.as_view(), name="client-history"),
    path(
        "pdf/fr/<int:pk>/",
        ClientStatementPDFView.as_view(),
        {"language": "fr"},
        name="client-statement-pdf-fr",
    ),
    path(
        "pdf/en/<int:pk>/",
        ClientStatementPDFView.as_view(),
        {"language": "en"},
        name="client-statement-pdf-en",
    ),
    path(
        "pdf/nl/<int:pk>/",
        ClientStatementPDFView.as_view(),
        {"language": "nl"},
        name="client-statement-pdf-nl",
    ),
    # GET Client detail, PUT update, DELETE
    path("<int:pk>/", ClientDetailEditDeleteView.as_view(), name="client-detail"),
    # GET generated code client
    path(
        "generate_code_client/",
        GenerateClientCodeView.as_view(),
        name="client-generate-code",
    ),
    # POST archiver le client
    path("archive/<int:pk>/", ArchiveToggleClientView.as_view(), name="client-archive"),
]
