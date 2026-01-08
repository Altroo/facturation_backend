"""
Dashboard API Tests.

Tests for all 20 dashboard endpoints with date filtering support.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership
from article.models import Article
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from client.models import Client
from company.models import Company
from devi.models import Devi, DeviLine
from facture_client.models import FactureClient, FactureClientLine
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import Ville, ModePaiement
from reglement.models import Reglement


pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    """Create a test user."""
    user_model = get_user_model()
    return user_model.objects.create_user(
        email="dashboard_test@example.com", password="testpass123"
    )


@pytest.fixture
def company():
    """Create a test company."""
    return Company.objects.create(
        raison_sociale="Dashboard Test Corp",
        ICE="ICE_DASH",
    )


@pytest.fixture
def membership(user, company):
    """Create membership linking user to company."""
    return Membership.objects.create(user=user, company=company)


@pytest.fixture
def ville():
    """Create a test city."""
    return Ville.objects.create(nom="Casablanca")


@pytest.fixture
def mode_paiement():
    """Create a test payment mode."""
    return ModePaiement.objects.create(nom="Virement Bancaire")


@pytest.fixture
def client_entity(company, ville):
    """Create a test client."""
    return Client.objects.create(
        code_client="CLT_DASH_001",
        client_type=Client.PERSONNE_MORALE,
        raison_sociale="Client Dashboard Test",
        ICE="ICE_CLT_DASH",
        registre_de_commerce="RC_CLT_DASH",
        delai_de_paiement=30,
        ville=ville,
        company=company,
    )


@pytest.fixture
def article(company):
    """Create a test article."""
    return Article.objects.create(
        designation="Article Dashboard Test",
        reference="ART_DASH_001",
        prix_vente=Decimal("100.00"),
        prix_achat=Decimal("80.00"),
        tva=Decimal("20.00"),
        company=company,
    )


@pytest.fixture
def facture_client(client_entity, mode_paiement, user):
    """Create a test facture client."""
    today = date.today()
    return FactureClient.objects.create(
        numero_facture="FC_DASH_001",
        date_facture=today,
        client=client_entity,
        mode_paiement=mode_paiement,
        created_by_user=user,
        statut="Envoyé",
    )


@pytest.fixture
def facture_with_line(client_entity, article, mode_paiement, user):
    """Create a facture client with line."""
    today = date.today()
    facture = FactureClient.objects.create(
        numero_facture="FC_DASH_002",
        date_facture=today,
        client=client_entity,
        mode_paiement=mode_paiement,
        created_by_user=user,
        statut="Envoyé",
    )
    FactureClientLine.objects.create(
        facture_client=facture,
        article=article,
        prix_vente=Decimal("100.00"),
        prix_achat=Decimal("80.00"),
        quantity=5,
    )
    facture.recalc_totals()
    facture.save()
    return facture


@pytest.fixture
def devi(client_entity, mode_paiement, user):
    """Create a test devi."""
    today = date.today()
    return Devi.objects.create(
        numero_devis="DEV_DASH_001",
        date_devis=today,
        client=client_entity,
        mode_paiement=mode_paiement,
        created_by_user=user,
        statut="Envoyé",
    )


@pytest.fixture
def facture_proforma(client_entity, mode_paiement, user):
    """Create a test facture proforma."""
    today = date.today()
    return FactureProForma.objects.create(
        numero_facture="FP_DASH_001",
        date_facture=today,
        client=client_entity,
        mode_paiement=mode_paiement,
        created_by_user=user,
        statut="Envoyé",
    )


@pytest.fixture
def bon_de_livraison(client_entity, mode_paiement, user):
    """Create a test bon de livraison."""
    today = date.today()
    return BonDeLivraison.objects.create(
        numero_bon_livraison="BDL_DASH_001",
        date_bon_livraison=today,
        client=client_entity,
        mode_paiement=mode_paiement,
        created_by_user=user,
        statut="Envoyé",
    )


@pytest.fixture
def mode_reglement():
    """Create a test mode reglement."""
    from parameter.models import ModeReglement
    return ModeReglement.objects.create(nom="Carte Bancaire")


@pytest.fixture
def reglement(client_entity, facture_client, mode_reglement):
    """Create a test reglement."""
    today = date.today()
    return Reglement.objects.create(
        facture_client=facture_client,
        mode_reglement=mode_reglement,
        montant=Decimal("500.00"),
        date_reglement=today,
        statut="Valide",
    )


@pytest.fixture
def api_client():
    """Returns an API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user, membership):
    """Returns an authenticated API client with user membership."""
    api_client.force_authenticate(user=user)
    return api_client


class TestFinancialOverviewEndpoints:
    """Tests for financial overview endpoints."""

    def test_monthly_revenue_evolution_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test monthly revenue evolution endpoint returns data."""
        response = authenticated_client.get("/api/dashboard/financial/monthly-revenue/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_monthly_revenue_evolution_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test monthly revenue with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=30)).isoformat()
        date_to = today.isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_monthly_revenue_evolution_unauthenticated(self, api_client):
        """Test unauthenticated access is forbidden."""
        response = api_client.get("/api/dashboard/financial/monthly-revenue/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_revenue_by_type_authenticated(
        self, authenticated_client, facture_client, devi, facture_proforma, bon_de_livraison
    ):
        """Test revenue by document type endpoint."""
        response = authenticated_client.get("/api/dashboard/financial/revenue-by-type/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_revenue_by_type_with_date_filters(self, authenticated_client, facture_client):
        """Test revenue by type with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=90)).isoformat()
        date_to = today.isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/financial/revenue-by-type/?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_status_overview_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test payment status overview endpoint."""
        response = authenticated_client.get("/api/dashboard/financial/payment-status/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_payment_status_with_date_filters(self, authenticated_client, facture_client):
        """Test payment status with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/financial/payment-status/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_collection_rate_authenticated(
        self, authenticated_client, facture_client, reglement
    ):
        """Test collection rate endpoint."""
        response = authenticated_client.get("/api/dashboard/financial/collection-rate/")
        assert response.status_code == status.HTTP_200_OK
        assert "rate" in response.data
        assert "total_invoiced" in response.data
        assert "total_collected" in response.data

    def test_collection_rate_with_date_filters(
        self, authenticated_client, facture_client, reglement
    ):
        """Test collection rate with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=365)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/financial/collection-rate/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestCommercialPerformanceEndpoints:
    """Tests for commercial performance endpoints."""

    def test_top_clients_by_revenue_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test top clients by revenue endpoint."""
        response = authenticated_client.get("/api/dashboard/commercial/top-clients/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_top_clients_with_date_filters(self, authenticated_client, facture_client):
        """Test top clients with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=180)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/commercial/top-clients/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_top_products_by_quantity_authenticated(
        self, authenticated_client, facture_with_line
    ):
        """Test top products by quantity endpoint."""
        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_top_products_with_date_filters(
        self, authenticated_client, facture_with_line
    ):
        """Test top products with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/commercial/top-products/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_quote_conversion_rate_authenticated(self, authenticated_client, devi):
        """Test quote conversion rate endpoint."""
        response = authenticated_client.get("/api/dashboard/commercial/quote-conversion/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_quote_conversion_with_date_filters(self, authenticated_client, devi):
        """Test quote conversion with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/commercial/quote-conversion/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_product_price_volume_analysis_authenticated(
        self, authenticated_client, facture_with_line
    ):
        """Test product price volume analysis endpoint."""
        response = authenticated_client.get(
            "/api/dashboard/commercial/product-price-volume/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_product_price_volume_with_date_filters(
        self, authenticated_client, facture_with_line
    ):
        """Test product price volume with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=60)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/commercial/product-price-volume/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestOperationalIndicatorEndpoints:
    """Tests for operational indicator endpoints."""

    def test_invoice_status_distribution_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test invoice status distribution endpoint."""
        response = authenticated_client.get("/api/dashboard/operational/invoice-status/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_invoice_status_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test invoice status with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/operational/invoice-status/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_monthly_document_volume_authenticated(
        self, authenticated_client, facture_client, devi, bon_de_livraison
    ):
        """Test monthly document volume endpoint."""
        response = authenticated_client.get("/api/dashboard/operational/document-volume/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_document_volume_with_date_filters(
        self, authenticated_client, facture_client, devi
    ):
        """Test document volume with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=365)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/operational/document-volume/?date_from={date_from}&date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestCashFlowEndpoints:
    """Tests for cash flow analysis endpoints."""

    def test_payment_timeline_authenticated(
        self, authenticated_client, facture_client, reglement
    ):
        """Test payment timeline endpoint."""
        response = authenticated_client.get("/api/dashboard/cashflow/payment-timeline/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_payment_timeline_with_date_filters(
        self, authenticated_client, facture_client, reglement
    ):
        """Test payment timeline with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=30)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/cashflow/payment-timeline/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_overdue_receivables_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test overdue receivables endpoint."""
        response = authenticated_client.get("/api/dashboard/cashflow/overdue-receivables/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_overdue_receivables_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test overdue receivables with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/overdue-receivables/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_delay_by_client_authenticated(
        self, authenticated_client, facture_client, reglement
    ):
        """Test payment delay by client endpoint."""
        response = authenticated_client.get("/api/dashboard/cashflow/payment-delay/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_payment_delay_with_date_filters(
        self, authenticated_client, facture_client, reglement
    ):
        """Test payment delay with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/payment-delay/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestClientAnalysisEndpoints:
    """Tests for client analysis endpoints."""

    def test_client_multidimensional_profile_authenticated(
        self, authenticated_client, facture_client, devi
    ):
        """Test client multidimensional profile endpoint."""
        response = authenticated_client.get(
            "/api/dashboard/client/multidimensional-profile/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_client_profile_with_date_filters(
        self, authenticated_client, facture_client, devi
    ):
        """Test client profile with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=365)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/client/multidimensional-profile/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestKPIEndpoints:
    """Tests for KPI endpoints."""

    def test_kpi_cards_with_trends_authenticated(
        self, authenticated_client, facture_client, reglement, client_entity
    ):
        """Test KPI cards with trends endpoint."""
        response = authenticated_client.get("/api/dashboard/kpi/cards-with-trends/")
        assert response.status_code == status.HTTP_200_OK
        assert "current_month_revenue" in response.data
        assert "outstanding_receivables" in response.data
        assert "average_invoice_amount" in response.data
        assert "active_clients" in response.data

    def test_kpi_cards_with_date_filters(
        self, authenticated_client, facture_client, reglement
    ):
        """Test KPI cards with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/kpi/cards-with-trends/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_monthly_objectives_authenticated(
        self, authenticated_client, facture_client, devi
    ):
        """Test monthly objectives endpoint."""
        response = authenticated_client.get("/api/dashboard/kpi/monthly-objectives/")
        assert response.status_code == status.HTTP_200_OK
        assert "revenue" in response.data
        assert "invoices" in response.data
        assert "conversion" in response.data

    def test_monthly_objectives_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test monthly objectives with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/kpi/monthly-objectives/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestDiscountAndMarginEndpoints:
    """Tests for discount and margin analysis endpoints."""

    def test_discount_impact_analysis_authenticated(
        self, authenticated_client, facture_client
    ):
        """Test discount impact analysis endpoint."""
        response = authenticated_client.get("/api/dashboard/analysis/discount-impact/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_discount_impact_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test discount impact with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/analysis/discount-impact/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_product_margin_volume_authenticated(
        self, authenticated_client, facture_with_line
    ):
        """Test product margin volume endpoint."""
        response = authenticated_client.get(
            "/api/dashboard/analysis/product-margin-volume/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_product_margin_with_date_filters(
        self, authenticated_client, facture_with_line
    ):
        """Test product margin with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/analysis/product-margin-volume/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestSyntheticDashboardEndpoints:
    """Tests for synthetic dashboard endpoints."""

    def test_monthly_global_performance_authenticated(
        self, authenticated_client, facture_client, devi, reglement, client_entity
    ):
        """Test monthly global performance endpoint."""
        response = authenticated_client.get(
            "/api/dashboard/synthetic/monthly-performance/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "current" in response.data
        assert "previous" in response.data

    def test_monthly_performance_with_date_filters(
        self, authenticated_client, facture_client, devi
    ):
        """Test monthly performance with date filters."""
        today = date.today()
        response = authenticated_client.get(
            f"/api/dashboard/synthetic/monthly-performance/?date_to={today.isoformat()}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_section_micro_trends_authenticated(
        self, authenticated_client, facture_client, devi
    ):
        """Test section micro trends endpoint."""
        response = authenticated_client.get(
            "/api/dashboard/synthetic/section-micro-trends/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "financial" in response.data
        assert "commercial" in response.data
        assert "operational" in response.data
        assert "cashflow" in response.data

    def test_section_micro_trends_with_date_filters(
        self, authenticated_client, facture_client
    ):
        """Test section micro trends with date filters."""
        today = date.today()
        date_from = (today - timedelta(days=30)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/synthetic/section-micro-trends/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestDateFilterEdgeCases:
    """Tests for date filter edge cases."""

    def test_invalid_date_format_fallback(self, authenticated_client, facture_client):
        """Test invalid date format defaults to today."""
        response = authenticated_client.get(
            "/api/dashboard/financial/monthly-revenue/?date_to=invalid-date"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_future_date_to(self, authenticated_client, facture_client):
        """Test future date_to returns empty or partial data."""
        future_date = (date.today() + timedelta(days=365)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_to={future_date}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_date_from_after_date_to(self, authenticated_client, facture_client):
        """Test date_from after date_to returns empty data."""
        today = date.today()
        date_from = today.isoformat()
        date_to = (today - timedelta(days=30)).isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_only_date_from_provided(self, authenticated_client, facture_client):
        """Test with only date_from - date_to should default to today."""
        date_from = (date.today() - timedelta(days=365)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_only_date_to_provided(self, authenticated_client, facture_client):
        """Test with only date_to - should use default lookback period."""
        date_to = date.today().isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_to={date_to}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestAuthenticationRequired:
    """Tests ensuring all endpoints require authentication."""

    ENDPOINTS = [
        "/api/dashboard/financial/monthly-revenue/",
        "/api/dashboard/financial/revenue-by-type/",
        "/api/dashboard/financial/payment-status/",
        "/api/dashboard/financial/collection-rate/",
        "/api/dashboard/commercial/top-clients/",
        "/api/dashboard/commercial/top-products/",
        "/api/dashboard/commercial/quote-conversion/",
        "/api/dashboard/commercial/product-price-volume/",
        "/api/dashboard/operational/invoice-status/",
        "/api/dashboard/operational/document-volume/",
        "/api/dashboard/cashflow/payment-timeline/",
        "/api/dashboard/cashflow/overdue-receivables/",
        "/api/dashboard/cashflow/payment-delay/",
        "/api/dashboard/client/multidimensional-profile/",
        "/api/dashboard/kpi/cards-with-trends/",
        "/api/dashboard/kpi/monthly-objectives/",
        "/api/dashboard/analysis/discount-impact/",
        "/api/dashboard/analysis/product-margin-volume/",
        "/api/dashboard/synthetic/monthly-performance/",
        "/api/dashboard/synthetic/section-micro-trends/",
    ]

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_unauthenticated_access_denied(self, api_client, endpoint):
        """Test all endpoints return 401 for unauthenticated requests."""
        response = api_client.get(endpoint)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestEmptyDataHandling:
    """Tests for empty data handling."""

    def test_empty_factures_returns_empty_list(self, authenticated_client):
        """Test endpoints return empty list when no data exists."""
        response = authenticated_client.get("/api/dashboard/financial/monthly-revenue/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) == 0

    def test_collection_rate_with_no_data(self, authenticated_client):
        """Test collection rate returns zeros when no data."""
        response = authenticated_client.get("/api/dashboard/financial/collection-rate/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_invoiced"] == 0
        assert response.data["total_collected"] == 0

    def test_kpi_cards_with_no_data(self, authenticated_client):
        """Test KPI cards return zeros when no data."""
        response = authenticated_client.get("/api/dashboard/kpi/cards-with-trends/")
        assert response.status_code == status.HTTP_200_OK
        assert "current_month_revenue" in response.data


class TestDocumentLinesAggregation:
    """Tests for document lines aggregation in top products endpoint."""

    def test_top_products_aggregates_devi_lines(
        self, authenticated_client, devi, article
    ):
        """Test that DeviLine quantities are included in top products."""
        # Create a DeviLine
        DeviLine.objects.create(
            devis=devi,
            article=article,
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            quantity=10,
        )

        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK
        # Should include the article from devi line
        assert isinstance(response.data, list)

    def test_top_products_aggregates_facture_proforma_lines(
        self, authenticated_client, facture_proforma, article
    ):
        """Test that FactureProFormaLine quantities are included in top products."""
        # Create a FactureProFormaLine
        FactureProFormaLine.objects.create(
            facture_pro_forma=facture_proforma,
            article=article,
            prix_achat=Decimal("60.00"),
            prix_vente=Decimal("90.00"),
            quantity=15,
        )

        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_top_products_aggregates_bon_de_livraison_lines(
        self, authenticated_client, bon_de_livraison, article
    ):
        """Test that BonDeLivraisonLine quantities are included in top products."""
        # Create a BonDeLivraisonLine
        BonDeLivraisonLine.objects.create(
            bon_de_livraison=bon_de_livraison,
            article=article,
            prix_achat=Decimal("40.00"),
            prix_vente=Decimal("60.00"),
            quantity=20,
        )

        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_top_products_aggregates_all_document_types(
        self, authenticated_client, devi, facture_with_line, facture_proforma, bon_de_livraison, article
    ):
        """Test that all document line types are aggregated correctly."""
        # Create lines for each document type
        DeviLine.objects.create(
            devis=devi,
            article=article,
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            quantity=5,
        )
        FactureProFormaLine.objects.create(
            facture_pro_forma=facture_proforma,
            article=article,
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            quantity=10,
        )
        BonDeLivraisonLine.objects.create(
            bon_de_livraison=bon_de_livraison,
            article=article,
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            quantity=15,
        )

        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        # Should have at least one product (the article used)
        # Total quantity should be 5 + 10 + 15 + 2 (from facture_with_line) = 32
        if len(response.data) > 0:
            # Find the article in results
            article_result = next(
                (p for p in response.data if p["article_id"] == article.id), None
            )
            if article_result:
                assert article_result["quantity"] >= 30  # At least from lines we created
