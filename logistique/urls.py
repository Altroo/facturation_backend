from django.urls import path

from .views import (
    BulkDeleteLogisticsOrderView,
    GenerateNumeroLogistiqueView,
    LogisticsDashboardView,
    LogisticsOrderDetailEditDeleteView,
    LogisticsOrderListCreateView,
    LogisticsResponsibleOptionsView,
    LogisticsOrderStatusUpdateView,
    LogisticsPaymentRejectView,
    LogisticsPaymentRequestView,
    LogisticsPaymentValidateView,
    LogisticsSwiftSentView,
)

app_name = "logistique"

urlpatterns = [
    path("", LogisticsOrderListCreateView.as_view(), name="logistique-list-create"),
    path("dashboard/", LogisticsDashboardView.as_view(), name="logistique-dashboard"),
    path(
        "bulk_delete/",
        BulkDeleteLogisticsOrderView.as_view(),
        name="logistique-bulk-delete",
    ),
    path(
        "generate_num_commande/",
        GenerateNumeroLogistiqueView.as_view(),
        name="generate-numero-logistique",
    ),
    path(
        "responsables/",
        LogisticsResponsibleOptionsView.as_view(),
        name="logistique-responsables",
    ),
    path(
        "<int:pk>/",
        LogisticsOrderDetailEditDeleteView.as_view(),
        name="logistique-detail",
    ),
    path(
        "switch_statut/<int:pk>/",
        LogisticsOrderStatusUpdateView.as_view(),
        name="logistique-statut-update",
    ),
    path(
        "<int:pk>/request_payment/",
        LogisticsPaymentRequestView.as_view(),
        name="logistique-request-payment",
    ),
    path(
        "<int:pk>/validate_payment/",
        LogisticsPaymentValidateView.as_view(),
        name="logistique-validate-payment",
    ),
    path(
        "<int:pk>/reject_payment/",
        LogisticsPaymentRejectView.as_view(),
        name="logistique-reject-payment",
    ),
    path(
        "<int:pk>/send_swift/",
        LogisticsSwiftSentView.as_view(),
        name="logistique-send-swift",
    ),
]
