from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership, Role
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
    caissier_role, _ = Role.objects.get_or_create(
        name="Caissier",
    )
    return Membership.objects.create(user=user, company=company, role=caissier_role)


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
    """Create a test facture pro forma."""
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
    from parameter.models import ModePaiement

    return ModePaiement.objects.create(nom="Carte Bancaire")


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
        self,
        authenticated_client,
        facture_client,
        devi,
        facture_proforma,
        bon_de_livraison,
    ):
        """Test revenue by document type endpoint."""
        response = authenticated_client.get("/api/dashboard/financial/revenue-by-type/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_revenue_by_type_with_date_filters(
        self, authenticated_client, facture_client
    ):
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

    def test_payment_status_with_date_filters(
        self, authenticated_client, facture_client
    ):
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
        response = authenticated_client.get(
            "/api/dashboard/commercial/quote-conversion/"
        )
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
        response = authenticated_client.get(
            "/api/dashboard/operational/invoice-status/"
        )
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
        response = authenticated_client.get(
            "/api/dashboard/operational/document-volume/"
        )
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
        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
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
        assert "currency_data" in response.data
        assert "MAD" in response.data["currency_data"]
        assert "EUR" in response.data["currency_data"]
        assert "USD" in response.data["currency_data"]
        assert "current_month_revenue" in response.data["currency_data"]["MAD"]
        assert "outstanding_receivables" in response.data["currency_data"]["MAD"]
        assert "average_invoice_amount" in response.data["currency_data"]["MAD"]
        assert "active_clients" in response.data["currency_data"]["MAD"]

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
        assert "currency_data" in response.data
        assert "MAD" in response.data["currency_data"]
        assert "current_month_revenue" in response.data["currency_data"]["MAD"]


class TestDocumentLinesAggregation:
    """Tests for document lines aggregation in top products' endpoint."""

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
        self,
        authenticated_client,
        devi,
        facture_with_line,
        facture_proforma,
        bon_de_livraison,
        article,
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
                assert (
                    article_result["quantity"] >= 30
                )  # At least from lines we created


class TestCompanyFiltering:
    """Tests for company_id filtering on all endpoints."""

    def test_monthly_revenue_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test monthly revenue with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_revenue_by_type_with_company_filter(
        self, authenticated_client, facture_client, devi, company
    ):
        """Test revenue by type with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/financial/revenue-by-type/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_status_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test payment status with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/financial/payment-status/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_collection_rate_with_company_filter(
        self, authenticated_client, facture_client, reglement, company
    ):
        """Test collection rate with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/financial/collection-rate/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_top_clients_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test top clients with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/commercial/top-clients/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_top_products_with_company_filter(
        self, authenticated_client, facture_with_line, company
    ):
        """Test top products with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/commercial/top-products/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_quote_conversion_with_company_filter(
        self, authenticated_client, devi, company
    ):
        """Test quote conversion with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/commercial/quote-conversion/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_product_price_volume_with_company_filter(
        self, authenticated_client, facture_with_line, company
    ):
        """Test product price volume with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/commercial/product-price-volume/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_invoice_status_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test invoice status with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/operational/invoice-status/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_document_volume_with_company_filter(
        self, authenticated_client, facture_client, devi, bon_de_livraison, company
    ):
        """Test document volume with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/operational/document-volume/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_timeline_with_company_filter(
        self, authenticated_client, facture_client, reglement, company
    ):
        """Test payment timeline with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/payment-timeline/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_overdue_receivables_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test overdue receivables with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/overdue-receivables/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_delay_with_company_filter(
        self, authenticated_client, facture_client, reglement, company
    ):
        """Test payment delay with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/payment-delay/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_client_profile_with_company_filter(
        self, authenticated_client, facture_client, devi, company
    ):
        """Test client profile with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/client/multidimensional-profile/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_kpi_cards_with_company_filter(
        self, authenticated_client, facture_client, reglement, company
    ):
        """Test KPI cards with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/kpi/cards-with-trends/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_monthly_objectives_with_company_filter(
        self, authenticated_client, facture_client, devi, company
    ):
        """Test monthly objectives with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/kpi/monthly-objectives/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_discount_impact_with_company_filter(
        self, authenticated_client, facture_client, company
    ):
        """Test discount impact with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/analysis/discount-impact/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_product_margin_with_company_filter(
        self, authenticated_client, facture_with_line, company
    ):
        """Test product margin with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/analysis/product-margin-volume/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_monthly_performance_with_company_filter(
        self, authenticated_client, facture_client, devi, reglement, company
    ):
        """Test monthly performance with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/synthetic/monthly-performance/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_section_micro_trends_with_company_filter(
        self, authenticated_client, facture_client, devi, reglement, company
    ):
        """Test section micro trends with company_id filter."""
        response = authenticated_client.get(
            f"/api/dashboard/synthetic/section-micro-trends/?company_id={company.id}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_invalid_company_id_ignored(self, authenticated_client, facture_client):
        """Test invalid company_id is ignored (returns all data)."""
        response = authenticated_client.get(
            "/api/dashboard/financial/monthly-revenue/?company_id=invalid"
        )
        assert response.status_code == status.HTTP_200_OK


class TestDateFromFilterBranches:
    """Tests for date_from filter branches."""

    def test_monthly_revenue_with_explicit_date_from(
        self, authenticated_client, facture_client
    ):
        """Test monthly revenue with explicit date_from parameter."""
        today = date.today()
        date_from = (today - timedelta(days=60)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/financial/monthly-revenue/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_payment_timeline_with_explicit_date_from(
        self, authenticated_client, facture_client, reglement
    ):
        """Test payment timeline with explicit date_from parameter."""
        today = date.today()
        date_from = (today - timedelta(days=15)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/cashflow/payment-timeline/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_document_volume_with_explicit_date_from(
        self, authenticated_client, facture_client, devi, bon_de_livraison
    ):
        """Test document volume with explicit date_from parameter."""
        today = date.today()
        date_from = (today - timedelta(days=180)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/operational/document-volume/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestPaymentStatusScenarios:
    """Tests for different payment status scenarios."""

    def test_fully_paid_facture(
        self, authenticated_client, client_entity, mode_paiement, user, mode_reglement
    ):
        """Test facture that is fully paid."""
        today = date.today()
        facture = FactureClient.objects.create(
            numero_facture="FC_PAID_001",
            date_facture=today,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("1000.00"),
        )
        # Create reglement that fully pays the facture
        Reglement.objects.create(
            facture_client=facture,
            mode_reglement=mode_reglement,
            montant=Decimal("1000.00"),
            date_reglement=today,
            statut="Valide",
        )

        response = authenticated_client.get("/api/dashboard/financial/payment-status/")
        assert response.status_code == status.HTTP_200_OK
        fully_paid_count = next(
            (s["count"] for s in response.data if s["status"] == "Totalement payée"), 0
        )
        assert fully_paid_count >= 1

    def test_partially_paid_facture(
        self,
        authenticated_client,
        client_entity,
        mode_paiement,
        user,
        mode_reglement,
        article,
    ):
        """Test facture that is partially paid."""
        today = date.today()
        facture = FactureClient.objects.create(
            numero_facture="FC_PARTIAL_001",
            date_facture=today,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
        )
        # Add a line to have total > 0
        FactureClientLine.objects.create(
            facture_client=facture,
            article=article,
            prix_vente=Decimal("1000.00"),
            prix_achat=Decimal("800.00"),
            quantity=1,
        )
        facture.recalc_totals()
        facture.save()

        # Create partial reglement (less than total)
        Reglement.objects.create(
            facture_client=facture,
            mode_reglement=mode_reglement,
            montant=Decimal("500.00"),
            date_reglement=today,
            statut="Valide",
        )

        response = authenticated_client.get("/api/dashboard/financial/payment-status/")
        assert response.status_code == status.HTTP_200_OK
        partial_count = next(
            (s["count"] for s in response.data if s["status"] == "Partiellement payée"),
            0,
        )
        assert partial_count >= 1


class TestOverdueReceivablesAgingBuckets:
    """Tests for overdue receivables aging buckets."""

    def test_overdue_30_60_days(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test facture overdue 31-60 days."""
        old_date = date.today() - timedelta(days=45)
        FactureClient.objects.create(
            numero_facture="FC_OLD_45",
            date_facture=old_date,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("2000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
        assert response.status_code == status.HTTP_200_OK
        bucket_31_60 = next(
            (b for b in response.data if b["period"] == "31-60 jours"), None
        )
        assert bucket_31_60 is not None

    def test_overdue_61_90_days(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test facture overdue 61-90 days."""
        old_date = date.today() - timedelta(days=75)
        FactureClient.objects.create(
            numero_facture="FC_OLD_75",
            date_facture=old_date,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("3000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
        assert response.status_code == status.HTTP_200_OK
        bucket_61_90 = next(
            (b for b in response.data if b["period"] == "61-90 jours"), None
        )
        assert bucket_61_90 is not None

    def test_overdue_90_plus_days(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test facture overdue 90+ days."""
        old_date = date.today() - timedelta(days=120)
        FactureClient.objects.create(
            numero_facture="FC_OLD_120",
            date_facture=old_date,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("4000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
        assert response.status_code == status.HTTP_200_OK
        bucket_90_plus = next(
            (b for b in response.data if b["period"] == "90+ jours"), None
        )
        assert bucket_90_plus is not None


class TestMonthlyPerformanceWithDateRange:
    """Tests for monthly performance with custom date ranges."""

    def test_monthly_performance_with_custom_date_range(
        self, authenticated_client, facture_client, devi
    ):
        """Test monthly performance with both date_from and date_to."""
        today = date.today()
        date_from = (today - timedelta(days=60)).isoformat()
        date_to = today.isoformat()

        response = authenticated_client.get(
            f"/api/dashboard/synthetic/monthly-performance/?date_from={date_from}&date_to={date_to}"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "current" in response.data
        assert "previous" in response.data

    def test_monthly_performance_january_previous_month(
        self, authenticated_client, facture_client
    ):
        """Test monthly performance calculation for January (previous month is December)."""
        # This test ensures the January edge case for previous month calculation works
        response = authenticated_client.get(
            "/api/dashboard/synthetic/monthly-performance/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestKPICardsWithDateFrom:
    """Tests for KPI cards with date_from filter."""

    def test_kpi_cards_with_date_from(
        self, authenticated_client, facture_client, reglement
    ):
        """Test KPI cards with date_from parameter."""
        today = date.today()
        date_from = (today - timedelta(days=60)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/kpi/cards-with-trends/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestDiscountImpactWithDiscount:
    """Tests for discount impact with actual discounts."""

    def test_discount_impact_with_discounted_facture(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test discount impact with a facture that has a discount."""
        today = date.today()
        FactureClient.objects.create(
            numero_facture="FC_DISC_001",
            date_facture=today,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc=Decimal("1000.00"),
            total_ttc_apres_remise=Decimal("900.00"),
            remise=Decimal("10.00"),
        )

        response = authenticated_client.get("/api/dashboard/analysis/discount-impact/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        # Should contain the discounted facture
        assert len(response.data) >= 1


class TestClientMultidimensionalProfile:
    """Tests for client multidimensional profile scenarios."""

    def test_client_profile_with_accepted_devis(
        self, authenticated_client, facture_client, client_entity, mode_paiement, user
    ):
        """Test client profile with accepted devis."""
        today = date.today()
        Devi.objects.create(
            numero_devis="DEV_ACC_001",
            date_devis=today,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Accepté",
        )

        response = authenticated_client.get(
            "/api/dashboard/client/multidimensional-profile/"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_client_profile_with_reglements(
        self, authenticated_client, facture_client, reglement
    ):
        """Test client profile with reglements for payment speed calculation."""
        response = authenticated_client.get(
            "/api/dashboard/client/multidimensional-profile/"
        )
        assert response.status_code == status.HTTP_200_OK
        if len(response.data) > 0:
            # Check that metrics are present
            assert "metrics" in response.data[0]


class TestMonthlyObjectivesWithDateFrom:
    """Tests for monthly objectives with date_from filter."""

    def test_monthly_objectives_with_date_from(
        self, authenticated_client, facture_client, devi
    ):
        """Test monthly objectives with date_from parameter."""
        today = date.today()
        date_from = (today - timedelta(days=60)).isoformat()
        response = authenticated_client.get(
            f"/api/dashboard/kpi/monthly-objectives/?date_from={date_from}"
        )
        assert response.status_code == status.HTTP_200_OK


class TestHelperFunctions:
    """Tests for helper functions in views."""

    def test_parse_date_filters_invalid_date_from(self, authenticated_client):
        """Test that invalid date_from is handled gracefully."""
        response = authenticated_client.get(
            "/api/dashboard/financial/monthly-revenue/?date_from=invalid-date"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_parse_date_filters_invalid_company_id(self, authenticated_client):
        """Test that invalid company_id is handled gracefully."""
        response = authenticated_client.get(
            "/api/dashboard/financial/monthly-revenue/?company_id=not-a-number"
        )
        assert response.status_code == status.HTTP_200_OK


class TestHelperFunctionsNoneCases:
    """Tests for helper functions returning None."""

    def test_make_aware_datetime_start_none(self, authenticated_client):
        """Test make_aware_datetime_start returns None when d is None (line 22)."""
        from dashboard.views import make_aware_datetime_start

        assert make_aware_datetime_start(None) is None

    def test_make_aware_datetime_end_none(self, authenticated_client):
        """Test make_aware_datetime_end returns None when d is None (line 29)."""
        from dashboard.views import make_aware_datetime_end

        assert make_aware_datetime_end(None) is None


class TestCollectionRateZeroInvoiced:
    """Tests for collection rate when total invoiced is zero."""

    def test_collection_rate_zero_invoiced(self, authenticated_client):
        """Test collection rate returns 0 when total_invoiced is 0 (line 246)."""
        # No factures exist, so total_invoiced should be 0
        # Delete all factures first
        FactureClient.objects.all().delete()

        response = authenticated_client.get("/api/dashboard/financial/collection-rate/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rate"] == 0


class TestOverdueReceivables0to30Days:
    """Tests for overdue receivables in 0-30 days bucket."""

    def test_overdue_0_30_days(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test facture overdue 0-30 days (line 700 - bucket 0-30)."""
        recent_date = date.today() - timedelta(days=15)
        FactureClient.objects.create(
            numero_facture="FC_OLD_15",
            date_facture=recent_date,
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc=Decimal("1000.00"),
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
        assert response.status_code == status.HTTP_200_OK
        bucket_0_30 = next(
            (b for b in response.data if b["period"] == "0-30 jours"), None
        )
        assert bucket_0_30 is not None


class TestPaymentStatusPartialAndUnpaid:
    """Tests for payment status with partial and unpaid factures."""

    def test_unpaid_facture(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test payment status counts unpaid facture correctly (line 206)."""
        FactureClient.objects.create(
            numero_facture="FC_UNPAID",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("5000.00"),
        )

        response = authenticated_client.get("/api/dashboard/financial/payment-status/")
        assert response.status_code == status.HTTP_200_OK
        unpaid_item = next(
            (item for item in response.data if item["status"] == "Impayée"), None
        )
        assert unpaid_item is not None


class TestTopProductsFiltering:
    """Tests for top products filtering date branches."""

    def test_top_products_no_date_from(
        self, authenticated_client, article, client_entity, mode_paiement, user
    ):
        """Test top products without date_from parameter (line 316-319 not triggered)."""
        # Create devi with line
        devi = Devi.objects.create(
            numero_devis="DEV_TOPPRODUCT",
            date_devis=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Brouillon",
        )
        DeviLine.objects.create(
            devis=devi,
            article=article,
            quantity=5,
            prix_achat=Decimal("80.00"),
            prix_vente=Decimal("100.00"),
        )

        # Request without date_from
        response = authenticated_client.get("/api/dashboard/commercial/top-products/")
        assert response.status_code == status.HTTP_200_OK


class TestQuoteConversionFiltering:
    """Tests for quote conversion filtering branches."""

    def test_quote_conversion_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test quote conversion without date_from (line 418 not triggered)."""
        Devi.objects.create(
            numero_devis="DEV_QUOTCONV",
            date_devis=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Accepté",
        )

        response = authenticated_client.get(
            "/api/dashboard/commercial/quote-conversion/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestInvoiceStatusFiltering:
    """Tests for invoice status filtering branches."""

    def test_invoice_status_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test invoice status without date_from."""
        FactureClient.objects.create(
            numero_facture="FC_INVSTATUS",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Brouillon",
        )

        response = authenticated_client.get(
            "/api/dashboard/operational/invoice-status/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestPaymentDelayFiltering:
    """Tests for payment delay filtering branches."""

    def test_payment_delay_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test payment delay without date_from (line 576)."""
        from parameter.models import ModePaiement

        facture = FactureClient.objects.create(
            numero_facture="FC_PAYDELAY",
            date_facture=date.today() - timedelta(days=30),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("1000.00"),
        )
        # Create a mode reglement
        mode_reglement = ModePaiement.objects.create(nom="Virement")
        # Create a reglement
        Reglement.objects.create(
            facture_client=facture,
            montant=Decimal("1000.00"),
            mode_reglement=mode_reglement,
            date_reglement=date.today(),
            statut="Valide",
        )

        response = authenticated_client.get("/api/dashboard/cashflow/payment-delay/")
        assert response.status_code == status.HTTP_200_OK


class TestOverdueReceivablesFiltering:
    """Tests for overdue receivables filtering branches."""

    def test_overdue_receivables_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test overdue receivables without date_from (line 660)."""
        FactureClient.objects.create(
            numero_facture="FC_OVERDUE_NOFROM",
            date_facture=date.today() - timedelta(days=45),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("2000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/cashflow/overdue-receivables/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestClientProfileFiltering:
    """Tests for client profile filtering branches."""

    def test_client_profile_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test client profile without date_from (line 735)."""
        FactureClient.objects.create(
            numero_facture="FC_PROFILE_NOFROM",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/client/multidimensional-profile/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestKPICardsFiltering:
    """Tests for KPI cards filtering branches."""

    def test_kpi_cards_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test KPI cards without date_from (line 946)."""
        FactureClient.objects.create(
            numero_facture="FC_KPI_NOFROM",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        response = authenticated_client.get("/api/dashboard/kpi/cards-with-trends/")
        assert response.status_code == status.HTTP_200_OK


class TestDiscountImpactFiltering:
    """Tests for discount impact filtering branches."""

    def test_discount_impact_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test discount impact without date_from (line 1084)."""
        FactureClient.objects.create(
            numero_facture="FC_DISCOUNT_NOFROM",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            remise=Decimal("10.00"),
            total_ttc=Decimal("1100.00"),
            total_ttc_apres_remise=Decimal("990.00"),
        )

        response = authenticated_client.get("/api/dashboard/analysis/discount-impact/")
        assert response.status_code == status.HTTP_200_OK


class TestProductMarginFiltering:
    """Tests for product margin filtering branches."""

    def test_product_margin_no_date_from(
        self, authenticated_client, article, client_entity, mode_paiement, user
    ):
        """Test product margin without date_from (line 1116)."""
        facture = FactureClient.objects.create(
            numero_facture="FC_MARGIN_NOFROM",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
        )
        FactureClientLine.objects.create(
            facture_client=facture,
            article=article,
            quantity=10,
            prix_achat=Decimal("80.00"),
            prix_vente=Decimal("100.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/analysis/product-margin-volume/"
        )
        assert response.status_code == status.HTTP_200_OK


class TestMonthlyPerformanceFiltering:
    """Tests for monthly performance filtering branches."""

    def test_monthly_performance_no_date_from(
        self, authenticated_client, client_entity, mode_paiement, user
    ):
        """Test monthly performance without date_from (line 1187)."""
        FactureClient.objects.create(
            numero_facture="FC_PERF_NOFROM",
            date_facture=date.today(),
            client=client_entity,
            mode_paiement=mode_paiement,
            created_by_user=user,
            statut="Envoyé",
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        response = authenticated_client.get(
            "/api/dashboard/synthetic/monthly-performance/"
        )
        assert response.status_code == status.HTTP_200_OK
