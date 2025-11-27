from django.urls import path

from .views import (
    ArticleListCreateView,
    ArticleDetailEditDeleteView,
    GenerateArticleReferenceCodeView,
    ArchiveToggleArticleView,
)

app_name = "article"

urlpatterns = [
    # GET Article list (paginated) & POST create
    path("", ArticleListCreateView.as_view(), name="article-list-create"),
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
]
