from django.urls import path

from . import views

urlpatterns = [
    # Monthly Objectives CRUD
    path(
        "objectives/",
        views.MonthlyObjectivesListCreateView.as_view(),
        name="objectives-list-create",
    ),
    path(
        "objectives/<int:pk>/",
        views.MonthlyObjectivesDetailView.as_view(),
        name="objectives-detail",
    ),
    path(
        "objectives/by-company/<int:company_id>/",
        views.MonthlyObjectivesByCompanyView.as_view(),
        name="objectives-by-company",
    ),
    # Financial Overview
    path(
        "financial/monthly-revenue/",
        views.MonthlyRevenueEvolutionView.as_view(),
        name="monthly-revenue-evolution",
    ),
    path(
        "financial/revenue-by-type/",
        views.RevenueByDocumentTypeView.as_view(),
        name="revenue-by-document-type",
    ),
    path(
        "financial/payment-status/",
        views.PaymentStatusOverviewView.as_view(),
        name="payment-status-overview",
    ),
    path(
        "financial/collection-rate/",
        views.CollectionRateView.as_view(),
        name="collection-rate",
    ),
    # Commercial Performance
    path(
        "commercial/top-clients/",
        views.TopClientsByRevenueView.as_view(),
        name="top-clients-by-revenue",
    ),
    path(
        "commercial/top-products/",
        views.TopProductsByQuantityView.as_view(),
        name="top-products-by-quantity",
    ),
    path(
        "commercial/quote-conversion/",
        views.QuoteConversionRateView.as_view(),
        name="quote-conversion-rate",
    ),
    path(
        "commercial/product-price-volume/",
        views.ProductPriceVolumeAnalysisView.as_view(),
        name="product-price-volume-analysis",
    ),
    # Operational Indicators
    path(
        "operational/invoice-status/",
        views.InvoiceStatusDistributionView.as_view(),
        name="invoice-status-distribution",
    ),
    path(
        "operational/document-volume/",
        views.MonthlyDocumentVolumeView.as_view(),
        name="monthly-document-volume",
    ),
    # Cash Flow Analysis
    path(
        "cashflow/payment-timeline/",
        views.PaymentTimelineView.as_view(),
        name="payment-timeline",
    ),
    path(
        "cashflow/overdue-receivables/",
        views.OverdueReceivablesView.as_view(),
        name="overdue-receivables",
    ),
    path(
        "cashflow/payment-delay/",
        views.PaymentDelayByClientView.as_view(),
        name="payment-delay-by-client",
    ),
    # Client Analysis
    path(
        "client/multidimensional-profile/",
        views.ClientMultidimensionalProfileView.as_view(),
        name="client-multidimensional-profile",
    ),
    # KPI Cards
    path(
        "kpi/cards-with-trends/",
        views.KPICardsWithTrendsView.as_view(),
        name="kpi-cards-with-trends",
    ),
    path(
        "kpi/monthly-objectives/",
        views.MonthlyObjectivesView.as_view(),
        name="monthly-objectives",
    ),
    # Discount and Margin Analysis
    path(
        "analysis/discount-impact/",
        views.DiscountImpactAnalysisView.as_view(),
        name="discount-impact-analysis",
    ),
    path(
        "analysis/product-margin-volume/",
        views.ProductMarginVolumeView.as_view(),
        name="product-margin-volume",
    ),
    # Synthetic Dashboards
    path(
        "synthetic/monthly-performance/",
        views.MonthlyGlobalPerformanceView.as_view(),
        name="monthly-global-performance",
    ),
    path(
        "synthetic/section-micro-trends/",
        views.SectionMicroTrendsView.as_view(),
        name="section-micro-trends",
    ),
]
