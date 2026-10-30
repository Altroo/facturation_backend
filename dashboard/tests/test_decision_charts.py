from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from bon_de_livraison.models import BonDeLivraison
from client.models import Client
from company.models import Company
from facture_avoir.models import FactureAvoir
from facture_client.models import FactureClient
from reglement.models import Reglement

pytestmark = pytest.mark.django_db
RECEIVABLES = "/api/dashboard/financial/receivables-by-client/"
DELIVERIES = "/api/dashboard/operational/uninvoiced-deliveries/"


@pytest.fixture
def context():
    user = CustomUser.objects.create_user(email="charts@example.test", password="test")
    company = Company.objects.create(raison_sociale="Charts", ICE="CHARTS")
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(user=user, company=company, role=role)
    customer = Client.objects.create(
        company=company, code_client="C1", client_type="PM", raison_sociale="Client A"
    )
    api = APIClient()
    api.force_authenticate(user)
    return api, company, customer, user


def document(model, customer, amount, **kwargs):
    number = "numero_facture" if model is FactureClient else "numero_bon_livraison"
    date_field = "date_facture" if model is FactureClient else "date_bon_livraison"
    values = {
        number: f"D{model.objects.count()+1}",
        date_field: timezone.localdate() - timedelta(days=20),
        "statut": "Envoyé" if model is FactureClient else "Accepté",
        "devise": "MAD",
    }
    values.update(kwargs)
    row = model.objects.create(client=customer, **values)
    model.objects.filter(pk=row.pk).update(total_ttc_apres_remise=Decimal(str(amount)))
    row.refresh_from_db()
    return row


def credit(invoice, amount, **kwargs):
    row = FactureAvoir.objects.create(
        client=invoice.client,
        facture_origine=invoice,
        numero_avoir=f"A{FactureAvoir.objects.count()+1}",
        date_avoir=kwargs.get("date_avoir", timezone.localdate()),
        motif_avoir="remise",
    )
    FactureAvoir.objects.filter(pk=row.pk).update(
        total_ttc_apres_remise=amount, statut=kwargs.get("statut", "Accepté")
    )


def get(api, company, endpoint, **params):
    response = api.get(endpoint, {"company_id": company.pk, **params})
    assert response.status_code == 200, response.data
    return response.json()


def test_receivables_subtract_valid_payments_and_credits_without_join_multiplication(
    context,
):
    api, company, customer, _ = context
    today = timezone.localdate()
    overdue = document(
        FactureClient, customer, 1000, date_echeance=today - timedelta(days=10)
    )
    for amount in [200, 100]:
        Reglement.objects.create(
            facture_client=overdue, montant=amount, date_reglement=today
        )
    Reglement.objects.create(
        facture_client=overdue, montant=500, statut="Annulé", date_reglement=today
    )
    Reglement.objects.create(
        facture_client=overdue, montant=50, date_reglement=today + timedelta(days=1)
    )
    credit(overdue, 100)
    credit(overdue, 50)
    credit(overdue, 150, statut="Brouillon")
    credit(overdue, 50, date_avoir=today + timedelta(days=1))
    document(FactureClient, customer, 400, date_echeance=today + timedelta(days=5))
    document(FactureClient, customer, 200, date_echeance=today)
    document(FactureClient, customer, 300)
    # The selected period selects documents, not an old snapshot of payments.
    data = get(
        api, company, RECEIVABLES, date_to=(today - timedelta(days=1)).isoformat()
    )
    assert data["as_of"] == today.isoformat()
    assert data["total_amount"] == 1450
    assert data["overdue_amount"] == 550
    assert data["invoice_count"] == 4
    assert data["clients"] == [
        {
            "client_id": customer.pk,
            "client_name": "Client A",
            "invoice_count": 4,
            "amount": 1450,
            "overdue": 550,
            "not_due": 600,
            "no_due_date": 300,
        }
    ]


def test_drafts_cancelled_paid_and_overpaid_invoices_do_not_inflate_receivables(
    context,
):
    api, company, customer, _ = context
    for state in ["Brouillon", "Annulé", "Refusé", "Expiré"]:
        document(FactureClient, customer, 5000, statut=state)
    for payment in [100, 120]:
        invoice = document(FactureClient, customer, 100)
        Reglement.objects.create(facture_client=invoice, montant=payment)
    invoice = document(FactureClient, customer, 100)
    credit(invoice, 100)
    document(FactureClient, customer, 200, statut="Accepté")
    data = get(api, company, RECEIVABLES)
    assert data["total_amount"] == 200
    assert data["invoice_count"] == 1


def test_top_five_is_ranked_but_summary_includes_all_clients(context):
    api, company, _, _ = context
    for index in range(7):
        customer = Client.objects.create(
            company=company,
            code_client=f"R{index}",
            client_type="PP",
            nom="Nom",
            prenom=str(index),
        )
        document(FactureClient, customer, (index + 1) * 100)
    data = get(api, company, RECEIVABLES)
    assert data["total_amount"] == 2800
    assert data["client_count"] == 7
    assert [row["amount"] for row in data["clients"]] == [700, 600, 500, 400, 300]
    assert data["clients"][0]["client_name"] == "Nom 6"


@pytest.mark.parametrize(
    "endpoint,model,date_field",
    [
        (RECEIVABLES, FactureClient, "date_facture"),
        (DELIVERIES, BonDeLivraison, "date_bon_livraison"),
    ],
)
def test_date_currency_client_project_and_company_scope(
    context, endpoint, model, date_field
):
    api, company, customer, _ = context
    today = timezone.localdate()
    other_company = Company.objects.create(raison_sociale="Private", ICE="PRIVATE")
    foreign = Client.objects.create(
        company=other_company, code_client="FOREIGN", client_type="PM"
    )
    another = Client.objects.create(
        company=company, code_client="OTHER", client_type="PM"
    )
    document(model, customer, 250, numero_bon_commande_client="VILLA-42")
    document(model, customer, 9000, numero_bon_commande_client="VILLA-42", devise="EUR")
    document(model, another, 8000, numero_bon_commande_client="VILLA-42")
    document(model, foreign, 7000, numero_bon_commande_client="VILLA-42")
    document(model, customer, 6000, numero_bon_commande_client="OTHER")
    document(
        model,
        customer,
        5000,
        numero_bon_commande_client="VILLA-42",
        **{date_field: today - timedelta(days=90)},
    )
    document(
        model,
        customer,
        4000,
        numero_bon_commande_client="VILLA-42",
        **{date_field: today + timedelta(days=1)},
    )
    data = get(
        api,
        company,
        endpoint,
        client_id=customer.pk,
        project="villa",
        date_from=(today - timedelta(days=30)).isoformat(),
        date_to=(today + timedelta(days=2)).isoformat(),
    )
    assert data["currency"] == "MAD"
    assert data["total_amount"] == 250
    euro = get(
        api, company, endpoint, client_id=customer.pk, project="villa", devise="EUR"
    )
    assert euro["currency"] == "EUR"
    assert euro["total_amount"] == 9000


def test_deliveries_age_boundaries_and_already_invoiced_exclusions(context):
    api, company, customer, _ = context
    today = timezone.localdate()
    for days in [0, 7, 8, 30, 31, 60, 61]:
        document(
            BonDeLivraison,
            customer,
            100,
            date_bon_livraison=today - timedelta(days=days),
        )
    for state in ["Brouillon", "Envoyé", "Facturé", "Annulé", "Refusé", "Expiré"]:
        document(BonDeLivraison, customer, 1000, statut=state)
    invoice = document(FactureClient, customer, 1000)
    document(BonDeLivraison, customer, 1000, source_facture_client=invoice)
    data = get(api, company, DELIVERIES)
    assert data["total_amount"] == 700
    assert data["total_count"] == 7
    assert [(b["key"], b["count"], b["amount"]) for b in data["buckets"]] == [
        ("0_7", 2, 200),
        ("8_30", 2, 200),
        ("31_60", 2, 200),
        ("over_60", 1, 100),
    ]


@pytest.mark.parametrize("endpoint", [RECEIVABLES, DELIVERIES])
def test_empty_and_company_permissions(context, endpoint):
    api, company, _, _ = context
    data = get(api, company, endpoint)
    assert data["total_amount"] == 0
    other_company = Company.objects.create(raison_sociale="Private", ICE="NOACCESS")
    assert api.get(endpoint, {"company_id": other_company.pk}).status_code == 403
    assert api.get(endpoint).status_code == 400
    assert APIClient().get(endpoint, {"company_id": company.pk}).status_code in [
        401,
        403,
    ]
