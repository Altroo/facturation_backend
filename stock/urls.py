from django.urls import path

from .views import (
    InventoryDetailView,
    InventoryListCreateView,
    InventoryValidateView,
    StockAdjustmentCreateView,
    StockBalanceListView,
    StockBalanceDetailView,
    StockMovementDetailView,
    StockMovementListView,
    StockReceiptActionView,
    StockReceiptListCreateView,
    StockReceiptDetailView,
)

app_name = "stock"

urlpatterns = [
    path("balances/", StockBalanceListView.as_view(), name="balances"),
    path("balances/<int:pk>/", StockBalanceDetailView.as_view(), name="balance-detail"),
    path("movements/", StockMovementListView.as_view(), name="movements"),
    path("movements/<int:pk>/", StockMovementDetailView.as_view(), name="movement-detail"),
    path("adjustments/", StockAdjustmentCreateView.as_view(), name="adjustments"),
    path("receipts/", StockReceiptListCreateView.as_view(), name="receipts"),
    path("receipts/<int:pk>/", StockReceiptDetailView.as_view(), name="receipt-detail"),
    path(
        "receipts/<int:pk>/<str:action>/",
        StockReceiptActionView.as_view(),
        name="receipt-action",
    ),
    path("inventories/", InventoryListCreateView.as_view(), name="inventories"),
    path("inventories/<int:pk>/", InventoryDetailView.as_view(), name="inventory-detail"),
    path(
        "inventories/<int:pk>/validate/",
        InventoryValidateView.as_view(),
        name="inventory-validate",
    ),
]
