from django.urls import path

from .views import (
    ArticleListCreateView,
    ArticleDetailEditDeleteView,
    GenerateArticleReferenceCodeView,
    ArchiveToggleArticleView,
    ImportArticlesView,
    SendCSVExampleEmailView,
    BulkDeleteArticleView,
    BulkArchiveArticleView,
)

app_name = "article"

urlpatterns = [
    # GET Article list (paginated) & POST create
    path("", ArticleListCreateView.as_view(), name="article-list-create"),
    # DELETE bulk delete articles
    path("bulk_delete/", BulkDeleteArticleView.as_view(), name="article-bulk-delete"),
    # PATCH bulk archive/unarchive articles
    path(
        "bulk_archive/", BulkArchiveArticleView.as_view(), name="article-bulk-archive"
    ),
    # GET Article detail, PUT update, DELETE
    path("<int:pk>/", ArticleDetailEditDeleteView.as_view(), name="article-detail"),
    # GET generated reference Article
    path(
        "generate_reference_article/",
        GenerateArticleReferenceCodeView.as_view(),
        name="article-generate-reference",
    ),
    # POST archiver le Article
    path(
        "archive/<int:pk>/", ArchiveToggleArticleView.as_view(), name="article-archive"
    ),
    # POST importer des articles depuis un fichier CSV
    path("import/", ImportArticlesView.as_view(), name="article-import"),
    # POST send CSV example email
    path(
        "send-csv-example-email/",
        SendCSVExampleEmailView.as_view(),
        name="article-send-csv-example-email",
    ),
]
