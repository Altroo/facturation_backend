from decimal import Decimal
from datetime import timedelta
import importlib
from unittest.mock import ANY, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import Marque, ModePaiement, Ville

from .admin import LogisticsOrderAdmin
from .models import (
    LogisticsOrder,
    LogisticsOrderEvent,
    LogisticsOrderProforma,
    LogisticsPaymentInstallment,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def logistics_company():
    return Company.objects.create(raison_sociale="Logistics Co", ICE="LOGICE")


@pytest.fixture
def logistics_roles():
    return {
        name: Role.objects.get_or_create(name=name)[0]
        for name in ["Caissier", "Comptable", "Logistique"]
    }


@pytest.fixture
def logistics_user(logistics_company, logistics_roles):
    user = CustomUser.objects.create_user(
        email="logistics@example.com",
        password="pass",
        first_name="Log",
        last_name="User",
    )
    Membership.objects.create(
        user=user,
        company=logistics_company,
        role=logistics_roles["Caissier"],
        can_change_document_status=True,
    )
    return user


@pytest.fixture
def comptable_user(logistics_company, logistics_roles):
    user = CustomUser.objects.create_user(
        email="comptable@example.com",
        password="pass",
        first_name="Compte",
        last_name="Able",
    )
    Membership.objects.create(
        user=user,
        company=logistics_company,
        role=logistics_roles["Comptable"],
    )
    return user


@pytest.fixture
def api_client(logistics_user):
    client = APIClient()
    client.force_authenticate(user=logistics_user)
    return client


def valid_logistics_payload(logistics_company, logistics_user, proforma, **overrides):
    payload = {
        "company_id": logistics_company.id,
        "proformas": [proforma.id],
        "date_prevue": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "origine_marchandise": "Espagne",
        "nature_marchandise": "Articles de test",
        "responsable": logistics_user.id,
    }
    payload.update(overrides)
    return payload


def supplier_proforma_payload(action="control", **overrides):
    payload = {
        "action": action,
        "numero_proforma_fournisseur": "PF-FOURN-001",
        "date_proforma_fournisseur": "2026-08-17",
        "montant_proforma_fournisseur": "400.00",
        "devise_proforma_fournisseur": "EUR",
        "incoterm": "FCA",
        "conditions_paiement": "50% à la commande, solde avant expédition",
        "delai_proforma_jours": "30",
        "ecart_prix_proforma": "false",
        "ecart_quantite_proforma": "false",
        "notes_ecarts_proforma": "",
        "proforma_fournisseur_file": SimpleUploadedFile(
            "proforma-fournisseur.pdf",
            b"%PDF-1.4 supplier proforma",
            content_type="application/pdf",
        ),
    }
    payload.update(overrides)
    return payload


def complete_supplier_proforma_step(api_client, order):
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])
    return api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(action="validate"),
        format="multipart",
    )


def prepare_valid_import_title(order):
    order.refresh_from_db()
    order.numero_domiciliation = "TI-2026-001"
    order.banque = "Banque test"
    order.montant_titre_importation = Decimal("400.00")
    order.devise_titre_importation = "EUR"
    order.date_titre_importation = timezone.localdate()
    order.statut_titre_importation = "À préparer"
    order.methode_paiement = "Virement"
    order.titre_importation_file = SimpleUploadedFile(
        "titre-import.pdf",
        b"%PDF-1.4 import title",
        content_type="application/pdf",
    )
    order.save(
        update_fields=[
            "numero_domiciliation",
            "banque",
            "montant_titre_importation",
            "devise_titre_importation",
            "date_titre_importation",
            "statut_titre_importation",
            "methode_paiement",
            "titre_importation_file",
            "date_updated",
        ]
    )


def payment_schedule_payload(order, **overrides):
    payload = {
        "echeancier": [
            {
                "date_echeance": (timezone.localdate() + timedelta(days=7)).isoformat(),
                "montant_prevu": str(order.montant_titre_importation),
                "devise": order.devise_titre_importation,
            }
        ]
    }
    payload.update(overrides)
    return payload


def payment_execution_payload(installment, **overrides):
    payload = {
        "echeance_id": installment.id,
        "date_paiement": "2026-07-04",
        "montant_paye": str(installment.montant_prevu),
        "devise_paiement": installment.devise,
        "banque_paiement": "Banque comptable",
        "reference_paiement": "SWIFT-001",
        "methode_paiement": "Virement",
        "commentaire_paiement": "Paiement fournisseur",
    }
    payload.update(overrides)
    return payload


def payment_validation_payload(installment, **overrides):
    payload = {
        "echeance_id": installment.id,
        "swift_file": SimpleUploadedFile(
            "swift.pdf",
            b"%PDF-1.4 swift",
            content_type="application/pdf",
        ),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def logistics_proformas(logistics_company, logistics_user):
    ville = Ville.objects.create(nom="Casablanca", company=logistics_company)
    client = Client.objects.create(
        code_client="LOG001",
        client_type="PM",
        raison_sociale="Client Logistique",
        ville=ville,
        company=logistics_company,
    )
    mode = ModePaiement.objects.create(nom="Virement", company=logistics_company)
    brand_a = Marque.objects.create(nom="Brand A", company=logistics_company)
    brand_b = Marque.objects.create(nom="Brand B", company=logistics_company)
    article_a = Article.objects.create(
        company=logistics_company,
        marque=brand_a,
        reference="A-001",
        designation="Article A",
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        tva=20,
    )
    article_b = Article.objects.create(
        company=logistics_company,
        marque=brand_b,
        reference="B-001",
        designation="Article B",
        prix_achat=Decimal("200.00"),
        prix_vente=Decimal("260.00"),
        tva=20,
    )
    proforma = FactureProForma.objects.create(
        numero_facture="P001/26",
        client=client,
        fournisseur="Supplier One",
        fournisseur_email="supplier@example.com",
        date_facture="2026-07-01",
        numero_bon_commande_client="PROJET-LOG-001",
        mode_paiement=mode,
        statut="Accepté",
        termes_paiement="30 jours fin de mois",
        created_by_user=logistics_user,
    )
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article_a,
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        quantity=2,
    )
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article_b,
        prix_achat=Decimal("200.00"),
        prix_vente=Decimal("260.00"),
        quantity=1,
    )
    return proforma, brand_a, brand_b


def create_logistics_order(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        valid_logistics_payload(logistics_company, logistics_user, proforma),
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response


def test_create_logistics_order_inherits_supplier_and_all_source_lines(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    response = create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["created"] == 1
    order = LogisticsOrder.objects.get()
    assert order.marque_id is None
    assert order.lignes.count() == 2
    assert order.fournisseur == "Supplier One"
    assert order.fournisseur_email == "supplier@example.com"
    assert order.conditions_paiement == "30 jours fin de mois"
    assert order.responsable == logistics_user
    assert order.statut_global == "À lancer"
    assert order.statut_commande_lancement == "À lancer"
    assert order.origine_marchandise == "Espagne"
    assert order.cout_achat == Decimal("400.000")
    assert order.cout_total == Decimal("400.000")
    assert set(order.lignes.values_list("marque_name", flat=True)) == {
        "Brand A",
        "Brand B",
    }
    assert order.lignes.first().project_reference == "PROJET-LOG-001"
    assert LogisticsOrderEvent.objects.filter(action="Création").count() == 1


def test_create_logistics_order_rejects_already_linked_source_lines(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    payload = valid_logistics_payload(logistics_company, logistics_user, proforma)
    url = reverse("logistique:logistique-list-create")

    first_response = api_client.post(url, payload, format="json")
    duplicate_response = api_client.post(url, payload, format="json")

    assert first_response.status_code == status.HTTP_201_CREATED
    assert duplicate_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "déjà lié" in str(duplicate_response.data["details"]["proformas"])
    assert LogisticsOrder.objects.count() == 1


def test_create_logistics_order_rejects_missing_required_fields(
    api_client, logistics_company, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        {"company_id": logistics_company.id, "proformas": [proforma.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "responsable" in response.data["details"]
    assert LogisticsOrder.objects.count() == 0


def test_create_logistics_order_rejects_zero_responsible(
    api_client, logistics_company, logistics_proformas
):
    proforma, _, _ = logistics_proformas

    response = api_client.post(
        reverse("logistique:logistique-list-create"),
        {
            "company_id": logistics_company.id,
            "proformas": [proforma.id],
            "responsable": 0,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "responsable" in response.data["details"]
    assert LogisticsOrder.objects.count() == 0


def test_create_logistics_order_requires_validated_client_order(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    proforma.statut = "Envoyé"
    proforma.save(update_fields=["statut"])

    response = api_client.post(
        reverse("logistique:logistique-list-create"),
        valid_logistics_payload(logistics_company, logistics_user, proforma),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "commandes client validées" in str(response.data["details"]["proformas"])
    assert LogisticsOrder.objects.count() == 0


def test_create_logistics_order_requires_source_supplier(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    proforma.fournisseur = ""
    proforma.save(update_fields=["fournisseur"])

    response = api_client.post(
        reverse("logistique:logistique-list-create"),
        valid_logistics_payload(logistics_company, logistics_user, proforma),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "fournisseur" in str(response.data["details"]["proformas"])
    assert LogisticsOrder.objects.count() == 0


def test_create_logistics_order_rejects_multiple_sources(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    payload = valid_logistics_payload(logistics_company, logistics_user, proforma)
    payload["proformas"] = [proforma.id, proforma.id]

    response = api_client.post(
        reverse("logistique:logistique-list-create"), payload, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "proformas" in response.data["details"]
    assert LogisticsOrder.objects.count() == 0


def test_logistics_source_preview_returns_inherited_source_data(
    api_client, logistics_company, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    url = reverse("logistique:logistique-source-preview")

    response = api_client.post(
        url,
        {"company_id": logistics_company.id, "proformas": [proforma.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert "brands" not in response.data
    source = response.data["proformas"][0]
    assert source["numero_facture"] == "P001/26"
    assert source["fournisseur"] == "Supplier One"
    assert source["fournisseur_email"] == "supplier@example.com"
    assert source["articles_count"] == 2
    assert source["total_quantity"] == Decimal("3")
    assert source["total_achat"] == Decimal("400")
    assert source["devise"] == "MAD"


def test_create_logistics_order_rejects_mixed_purchase_currencies(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, brand_a, _ = logistics_proformas
    line = FactureProFormaLine.objects.filter(article__marque=brand_a).first()
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=line.article,
        prix_achat=Decimal("50.00"),
        devise_prix_achat="EUR",
        prix_vente=Decimal("75.00"),
        devise_prix_vente="EUR",
        quantity=1,
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        valid_logistics_payload(logistics_company, logistics_user, proforma),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "plusieurs devises d'achat" in str(response.data["details"]["proformas"])
    assert LogisticsOrder.objects.count() == 0


def test_logistics_list_returns_dashboard_stats(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.get(
        url,
        {"company_id": logistics_company.id, "pagination": "true"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["stats"]["total_commandes"] == 1
    assert response.data["stats"]["commandes_en_cours"] == 1
    assert response.data["stats"]["couts_logistiques"] == Decimal("400.00")
    assert response.data["stats"]["couts_detail"]["transport"] == Decimal("0.00")
    assert response.data["stats"]["statuts_workflow"] == [
        {"statut": "À lancer", "total": 1}
    ]
    assert response.data["stats"]["statuts_paiement"] == [
        {"statut_paiement": "Non demandé", "total": 1}
    ]
    assert response.data["stats"]["fournisseurs"] == [
        {"fournisseur": "Supplier One"}
    ]
    assert response.data["stats"]["kpi_fournisseurs"] == [
        {
            "fournisseur": "Supplier One",
            "total_commandes": 1,
            "cout_total": Decimal("400.00"),
        }
    ]
    assert len(response.data["stats"]["monthly_flow"]) == 6
    assert {
        "month",
        "commandes",
        "livraisons",
        "paiements",
        "cout_total",
    }.issubset(response.data["stats"]["monthly_flow"][-1].keys())


def test_logistics_filters_accept_selectable_multi_values(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-SUPPLIER-TWO",
        fournisseur="Supplier Two",
        statut="Titre d'Importation",
        statut_global="En cours",
        statut_commande_lancement="Terminée",
        statut_proforma_conformite="Validée",
        statut_paiement="Validé",
        statut_titre_importation="Titre d'import validé – En attente de paiement",
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.get(
        url,
        {
            "company_id": logistics_company.id,
            "pagination": "true",
            "fournisseur": "Supplier One,Supplier Two",
            "statut_global": "À lancer,En cours",
            "statut_paiement": "Non demandé,Validé",
            "statut_titre_importation": "À préparer,Titre d'import validé – En attente de paiement",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2


def test_legacy_status_filter_keeps_original_semantics(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.get()
    order.statut = "Proforma"
    order.save(update_fields=["statut"])

    response = api_client.get(
        reverse("logistique:logistique-list-create"),
        {
            "company_id": logistics_company.id,
            "pagination": "true",
            "statut": "Proforma",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["statut"] == "Proforma"


def test_manager_records_proforma_request_and_completes_launch_step(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    follow_up = timezone.localdate() + timedelta(days=3)

    response = api_client.post(
        reverse("logistique:logistique-record-proforma-request", args=[order.id]),
        {"prochaine_relance_proforma": follow_up.isoformat()},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_global == "En attente externe"
    assert order.statut_commande_lancement == "Terminée"
    assert order.proforma_demandee_le is not None
    assert order.proforma_demandee_par == logistics_user
    assert order.prochaine_relance_proforma == follow_up
    assert order.events.filter(action="Demande de proforma").exists()


@pytest.mark.parametrize(
    ("launch_status", "expected_global_status"),
    [
        ("À lancer", "À lancer"),
        ("En cours", "En cours"),
        ("En attente proforma", "En attente externe"),
        ("Bloquée", "Bloqué"),
    ],
)
def test_part_one_substatuses_drive_global_status(
    logistics_company, launch_status, expected_global_status
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande=f"LOG-{launch_status}",
        statut_commande_lancement=launch_status,
    )

    assert order.calculate_global_status() == expected_global_status


@pytest.mark.parametrize(
    ("launch_status", "expected_global_status", "reference"),
    [
        ("À lancer", "À lancer", "START"),
        ("En cours", "En cours", "ACTIVE"),
        ("En attente proforma", "En attente externe", "WAIT"),
        ("Bloquée", "Bloqué", "BLOCK"),
    ],
)
def test_manager_can_apply_part_one_substatuses_in_application(
    api_client, logistics_company, launch_status, expected_global_status, reference
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande=f"LOG-API-{reference}",
    )

    response = api_client.patch(
        reverse("logistique:logistique-launch-status-update", args=[order.id]),
        {"statut": launch_status},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_commande_lancement == launch_status
    assert order.statut_global == expected_global_status
    if launch_status != "À lancer":
        assert order.events.filter(
            action="Changement statut Commande & lancement",
            new_value=launch_status,
        ).exists()


def test_launch_step_can_only_finish_through_recorded_proforma_request(
    api_client, logistics_company
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LAUNCH-FINISH-GATE",
    )
    url = reverse("logistique:logistique-launch-status-update", args=[order.id])

    premature_response = api_client.patch(
        url, {"statut": "Terminée"}, format="json"
    )
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["proforma_demandee_le"])
    completed_response = api_client.patch(
        url, {"statut": "Terminée"}, format="json"
    )
    regression_response = api_client.patch(
        url, {"statut": "En cours"}, format="json"
    )

    assert premature_response.status_code == status.HTTP_400_BAD_REQUEST
    assert completed_response.status_code == status.HTTP_200_OK
    assert regression_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_commande_lancement == "Terminée"


def test_overdue_proforma_follow_up_drives_global_status(logistics_company):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-FOLLOW-UP-LATE",
        statut_commande_lancement="Terminée",
        statut_proforma_conformite="En attente",
        prochaine_relance_proforma=timezone.localdate() - timedelta(days=1),
    )

    assert order.calculate_global_status() == "En retard"


def test_supplier_proforma_review_requires_completed_launch_step(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()

    response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(),
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Commande & lancement" in str(response.data["details"]["proforma"])


def test_supplier_proforma_correction_requires_a_documented_variance(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])

    response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(action="request_correction"),
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "variances" in response.data["details"]
    assert "notes_ecarts_proforma" in response.data["details"]


def test_supplier_proforma_review_requires_positive_amount_and_file(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])
    payload = supplier_proforma_payload()
    payload.pop("proforma_fournisseur_file")

    missing_file_response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        payload,
        format="multipart",
    )
    invalid_amount_response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(montant_proforma_fournisseur="0"),
        format="multipart",
    )

    assert missing_file_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "proforma_fournisseur_file" in missing_file_response.data["details"]
    assert invalid_amount_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "montant_proforma_fournisseur" in invalid_amount_response.data["details"]


def test_supplier_proforma_review_rejects_unsupported_file_type(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])

    response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(
            proforma_fournisseur_file=SimpleUploadedFile(
                "proforma.txt", b"not a supported document", content_type="text/plain"
            )
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "proforma_fournisseur_file" in response.data["details"]


def test_supplier_proforma_correction_sets_external_waiting_status(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])

    response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(
            action="request_correction",
            ecart_prix_proforma="true",
            notes_ecarts_proforma="Le prix unitaire diffère de la commande client.",
        ),
        format="multipart",
    )

    assert response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_proforma_conformite == "Correction demandée"
    assert order.statut_global == "En attente externe"
    assert order.ecart_prix_proforma is True
    assert order.proforma_controlee_par == logistics_user
    assert order.events.filter(action="Correction proforma demandée").exists()


def test_supplier_proforma_validation_completes_second_step(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_commande_lancement = "Terminée"
    order.proforma_demandee_le = timezone.now()
    order.save(update_fields=["statut_commande_lancement", "proforma_demandee_le"])

    response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(action="validate"),
        format="multipart",
    )

    assert response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_proforma_conformite == "Validée"
    assert order.statut_global == "En cours"
    assert order.statut == "Validation"
    assert order.proforma_fournisseur_file
    assert order.proforma_validee_par == logistics_user
    assert order.is_proforma_step_complete is True
    assert response.data["is_proforma_step_complete"] is True
    assert order.events.filter(action="Validation proforma fournisseur").exists()


@pytest.mark.parametrize(
    ("legacy_status", "reference_suffix"),
    [("Titre d'Importation", "TI"), ("Validation", "VALID")],
)
def test_legacy_downstream_order_keeps_proforma_step_complete(
    api_client, logistics_company, legacy_status, reference_suffix
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande=f"LOG-LEGACY-{reference_suffix}",
        statut=legacy_status,
        statut_global="En cours",
        statut_commande_lancement="Terminée",
        statut_proforma_conformite="En attente",
    )

    response = api_client.get(reverse("logistique:logistique-detail", args=[order.id]))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["statut_proforma_conformite"] == "Validée"
    assert response.data["is_proforma_step_complete"] is True


def test_validated_proforma_fields_cannot_be_changed_by_generic_update(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    validation_response = complete_supplier_proforma_step(api_client, order)
    assert validation_response.status_code == status.HTTP_200_OK

    response = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"incoterm": "CIF"},
        format="json",
    )
    replacement_response = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {
            "proforma_fournisseur_file": SimpleUploadedFile(
                "replacement.pdf",
                b"%PDF-1.4 replacement",
                content_type="application/pdf",
            )
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "incoterm" in response.data["details"]
    assert replacement_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "proforma_fournisseur_file" in replacement_response.data["details"]


def test_cancelled_order_blocks_launch_and_proforma_workflows(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    order.statut_global = "Annulé"
    order.save(update_fields=["statut_global"])

    launch_response = api_client.post(
        reverse("logistique:logistique-record-proforma-request", args=[order.id]),
        {
            "prochaine_relance_proforma": (
                timezone.localdate() + timedelta(days=3)
            ).isoformat()
        },
        format="json",
    )
    order.statut_commande_lancement = "Terminée"
    order.save(update_fields=["statut_commande_lancement"])
    proforma_response = api_client.post(
        reverse("logistique:logistique-review-supplier-proforma", args=[order.id]),
        supplier_proforma_payload(),
        format="multipart",
    )
    edit_response = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"transport": "Route"},
        format="json",
    )

    assert launch_response.status_code == status.HTTP_400_BAD_REQUEST
    assert proforma_response.status_code == status.HTTP_400_BAD_REQUEST
    assert edit_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_global == "Annulé"


def test_global_status_changes_require_specific_permission(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.order_by("id").first()
    Membership.objects.filter(user=logistics_user, company=logistics_company).update(
        can_change_document_status=False
    )

    response = api_client.patch(
        reverse("logistique:logistique-global-status-update", args=[order.id]),
        {"statut": "Annulé"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    order.refresh_from_db()
    assert order.statut_global != "Annulé"


def test_reopened_legacy_cancelled_order_stays_reopened(api_client, logistics_company):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-REOPEN-001",
        statut="Annulé",
        statut_global="Annulé",
        statut_commande_lancement="Terminée",
    )

    response = api_client.patch(
        reverse("logistique:logistique-global-status-update", args=[order.id]),
        {"statut": "Rouvert"},
        format="json",
    )
    detail_response = api_client.get(
        reverse("logistique:logistique-detail", args=[order.id])
    )

    assert response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["statut_global"] == "Rouvert"


def test_only_cancelled_order_can_be_reopened(api_client, logistics_company):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-REOPEN-002",
        statut_global="En cours",
    )

    response = api_client.patch(
        reverse("logistique:logistique-global-status-update", args=[order.id]),
        {"statut": "Rouvert"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_global == "En cours"


def test_legacy_status_transition_requires_completed_payment(api_client, logistics_company):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LEGACY-STAGE",
        statut="Envoi SWIFT / Draft LC",
        statut_global="En cours",
        statut_commande_lancement="Terminée",
        statut_proforma_conformite="En attente",
    )

    blocked_response = api_client.patch(
        reverse("logistique:logistique-statut-update", args=[order.id]),
        {"statut": "Production"},
        format="json",
    )

    order.statut_paiement = "Validé"
    order.save(update_fields=["statut_paiement"])
    response = api_client.patch(
        reverse("logistique:logistique-statut-update", args=[order.id]),
        {"statut": "Production"},
        format="json",
    )

    assert blocked_response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut == "Production"
    assert order.events.filter(
        action="Changement de statut", new_value="Production"
    ).exists()


@pytest.mark.parametrize("requested_status", ["Titre d'Importation", "Production"])
def test_legacy_status_cannot_skip_supplier_proforma(
    api_client, logistics_company, requested_status
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LEGACY-GATE",
        statut="Réception commande",
        statut_commande_lancement="Terminée",
        statut_proforma_conformite="En attente",
    )

    response = api_client.patch(
        reverse("logistique:logistique-statut-update", args=[order.id]),
        {"statut": requested_status},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut == "Réception commande"


def test_detail_calculates_overdue_status_without_writing_on_get(
    api_client, logistics_company
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LATE-001",
        date_prevue=timezone.localdate() - timedelta(days=1),
        statut="Réception commande",
        statut_global="À lancer",
        statut_commande_lancement="À lancer",
    )

    response = api_client.get(reverse("logistique:logistique-detail", args=[order.id]))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["statut_global"] == "En retard"
    order.refresh_from_db()
    assert order.statut_global == "À lancer"


def test_delivered_kpi_includes_legacy_delivery_stage(api_client, logistics_company):
    LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-DELIVERED-001",
        statut="Livraison client",
        statut_global="En cours",
        statut_commande_lancement="Terminée",
        date_reelle=timezone.localdate(),
    )

    response = api_client.get(
        reverse("logistique:logistique-dashboard"),
        {"company_id": logistics_company.id},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["livraisons"] == 1


def test_part_three_full_payment_flow_matches_docx(
    api_client,
    logistics_company,
    logistics_user,
    logistics_proformas,
    comptable_user,
    django_capture_on_commit_callbacks,
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.first()

    proforma_response = complete_supplier_proforma_step(api_client, order)
    assert proforma_response.status_code == status.HTTP_200_OK
    prepare_valid_import_title(order)

    request_url = reverse("logistique:logistique-request-payment", args=[order.id])
    comptable_client = APIClient()
    comptable_client.force_authenticate(user=comptable_user)
    non_owner_request = comptable_client.post(
        request_url, payment_schedule_payload(order), format="json"
    )
    assert non_owner_request.status_code == status.HTTP_403_FORBIDDEN
    with django_capture_on_commit_callbacks(execute=True):
        request_response = api_client.post(
            request_url, payment_schedule_payload(order), format="json"
        )
    assert request_response.status_code == status.HTTP_200_OK, request_response.data
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.statut_titre_importation == "Titre d'import validé – En attente de paiement"
    assert order.statut_banque_paiement == "En validation"
    assert order.statut_traitement_paiement == "Paiement à traiter"
    assert order.paiement_assigne_a == comptable_user
    assert order.demande_paiement_email_statut == "Envoyé"
    assert order.demande_paiement_envoyee_le is not None
    assert len(mail.outbox) == 1
    accounting_email = mail.outbox[0]
    assert accounting_email.subject == (
        f"Paiement à effectuer – Dossier Import {order.numero_commande}"
    )
    assert accounting_email.to == [comptable_user.email]
    assert f"Référence dossier : {order.numero_commande}" in accounting_email.body
    assert "Fournisseur : Supplier One" in accounting_email.body
    assert "Montant : 400.00 EUR" in accounting_email.body
    assert "Référence titre d'importation : TI-2026-001" in accounting_email.body
    assert f"/dashboard/logistique/{order.id}?company_id={order.company_id}" in accounting_email.body
    assert len(accounting_email.attachments) == 2
    assert comptable_user.notifications.filter(
        title="Effectuer le paiement fournisseur", object_id=order.id
    ).exists()
    installment = order.echeances_paiement.get()

    unauthorized_start = api_client.post(
        reverse("logistique:logistique-start-payment", args=[order.id]),
        {"echeance_id": installment.id},
        format="json",
    )
    assert unauthorized_start.status_code == status.HTTP_403_FORBIDDEN
    start_response = comptable_client.post(
        reverse("logistique:logistique-start-payment", args=[order.id]),
        {"echeance_id": installment.id},
        format="json",
    )
    assert start_response.status_code == status.HTTP_200_OK

    execution_response = comptable_client.post(
        reverse("logistique:logistique-record-payment-execution", args=[order.id]),
        payment_execution_payload(installment, methode_paiement="Remise documentaire"),
        format="json",
    )
    assert execution_response.status_code == status.HTTP_200_OK, execution_response.data
    installment.refresh_from_db()
    assert installment.statut_traitement == "Paiement effectué – Justificatif à joindre"
    assert installment.methode_paiement == "Remise documentaire"
    order.refresh_from_db()
    assert order.methode_paiement == "Virement"

    validate_url = reverse("logistique:logistique-validate-payment", args=[order.id])
    validate_response = comptable_client.post(
        validate_url,
        payment_validation_payload(installment),
        format="multipart",
    )

    assert validate_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut == "Paiement effectué"
    assert order.statut_paiement == "Validé"
    assert order.statut_banque_paiement == "Exécuté"
    assert order.statut_traitement_paiement == "Paiement validé"
    assert order.solde_restant == Decimal("0")
    assert order.paiement_assigne_a is None
    assert order.paiement_valide_par == comptable_user
    assert order.reference_paiement == "SWIFT-001"
    assert order.devise_paiement == "EUR"
    assert order.banque_paiement == "Banque comptable"
    assert order.commentaire_paiement == "Paiement fournisseur"
    assert order.swift_file
    assert order.date_upload_swift is not None
    assert order.events.filter(action="Validation paiement").exists()
    expected_message = (
        f"Le paiement du dossier {order.numero_commande} a été validé par le Service "
        "Comptable. Le SWIFT / LC est disponible. Vous pouvez poursuivre le traitement "
        "de la commande."
    )
    assert logistics_user.notifications.filter(message=expected_message).exists()

    send_url = reverse("logistique:logistique-send-swift", args=[order.id])
    non_owner_send = comptable_client.post(
        send_url, {"echeance_id": installment.id}, format="json"
    )
    assert non_owner_send.status_code == status.HTTP_403_FORBIDDEN
    with django_capture_on_commit_callbacks(execute=True):
        first_send = api_client.post(
            send_url, {"echeance_id": installment.id}, format="json"
        )
    duplicate_send = api_client.post(
        send_url, {"echeance_id": installment.id}, format="json"
    )
    assert first_send.status_code == status.HTTP_200_OK
    assert duplicate_send.status_code == status.HTTP_400_BAD_REQUEST
    installment.refresh_from_db()
    assert installment.preuve_email_statut == "Envoyé"
    assert installment.preuve_email_destinataire == "supplier@example.com"
    assert installment.preuve_envoyee_fournisseur_le is not None
    assert len(mail.outbox) == 2
    supplier_email = mail.outbox[1]
    assert supplier_email.to == ["supplier@example.com"]
    assert supplier_email.subject == (
        f"Justificatif de paiement – Dossier import {order.numero_commande}"
    )
    assert "Montant payé : 400.00 EUR" in supplier_email.body
    assert "Référence bancaire : SWIFT-001" in supplier_email.body
    assert len(supplier_email.attachments) == 1

    confirm_url = reverse(
        "logistique:logistique-confirm-payment-receipt", args=[order.id]
    )
    confirm_response = api_client.post(
        confirm_url, {"echeance_id": installment.id}, format="json"
    )
    assert confirm_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_banque_paiement == "Confirmé"
    assert order.paiement_confirme_reception_par == logistics_user


def test_payment_request_requires_a_complete_validated_import_title(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.first()
    assert (
        complete_supplier_proforma_step(api_client, order).status_code
        == status.HTTP_200_OK
    )

    response = api_client.post(
        reverse("logistique:logistique-request-payment", args=[order.id]),
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_paiement == "Non demandé"
    assert not order.demande_paiement_envoyee_le


def test_payment_validation_requires_execution_and_proof(
    api_client, logistics_company, comptable_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-PAYMENT-REQUIRED",
        statut_paiement="En attente",
        paiement_assigne_a=comptable_user,
        montant_titre_importation=Decimal("400.00"),
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("400.00"),
        devise="EUR",
    )
    url = reverse("logistique:logistique-validate-payment", args=[order.id])
    comptable_client = APIClient()
    comptable_client.force_authenticate(user=comptable_user)

    before_execution = comptable_client.post(
        url, payment_validation_payload(installment), format="multipart"
    )
    installment.statut_traitement = "Paiement effectué – Justificatif à joindre"
    installment.save(update_fields=["statut_traitement"])
    without_proof = payment_validation_payload(installment)
    without_proof.pop("swift_file")
    proof_response = comptable_client.post(url, without_proof, format="multipart")

    assert before_execution.status_code == status.HTTP_400_BAD_REQUEST
    assert proof_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"


def test_generic_edit_cannot_bypass_title_or_payment_workflow(
    api_client, logistics_company, logistics_user
):
    transmitted = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-TITLE-LOCKED",
        statut_paiement="En attente",
        responsable=logistics_user,
    )
    fresh = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-PAYMENT-DEDICATED",
        responsable=logistics_user,
    )

    title_response = api_client.put(
        reverse("logistique:logistique-detail", args=[transmitted.id]),
        {"banque": "Banque modifiée"},
        format="json",
    )
    payment_response = api_client.put(
        reverse("logistique:logistique-detail", args=[fresh.id]),
        {"date_paiement": "2026-08-18"},
        format="json",
    )
    title_method_response = api_client.put(
        reverse("logistique:logistique-detail", args=[fresh.id]),
        {"methode_paiement": "Virement"},
        format="json",
    )
    controlled_status_response = api_client.put(
        reverse("logistique:logistique-detail", args=[fresh.id]),
        {"statut_titre_importation": "Titre d'import validé – En attente de paiement"},
        format="json",
    )

    assert title_response.status_code == status.HTTP_400_BAD_REQUEST
    assert payment_response.status_code == status.HTTP_400_BAD_REQUEST
    assert title_method_response.status_code == status.HTTP_200_OK
    assert controlled_status_response.status_code == status.HTTP_400_BAD_REQUEST


def test_generic_document_upload_rejects_unsupported_files(
    api_client, logistics_company, logistics_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-DOCUMENT-VALIDATION",
        responsable=logistics_user,
    )

    response = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {
            "titre_importation_file": SimpleUploadedFile(
                "titre-import.exe",
                b"unsupported executable",
                content_type="application/octet-stream",
            )
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "titre_importation_file" in response.data["details"]


def test_only_assigned_responsible_can_edit_import_title(
    api_client, logistics_company, logistics_roles, logistics_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-TITLE-OWNER",
        responsable=logistics_user,
    )
    other_manager = CustomUser.objects.create_user(
        email="other-manager@example.com",
        password="pass",
    )
    Membership.objects.create(
        user=other_manager,
        company=logistics_company,
        role=logistics_roles["Logistique"],
    )
    manager_client = APIClient()
    manager_client.force_authenticate(user=other_manager)

    denied_title = manager_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"banque": "Banque non autorisée"},
        format="json",
    )
    allowed_general = manager_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"transport": "Route"},
        format="json",
    )
    allowed_title = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"banque": "Banque du responsable"},
        format="json",
    )

    assert denied_title.status_code == status.HTTP_403_FORBIDDEN
    assert allowed_general.status_code == status.HTTP_200_OK
    assert allowed_title.status_code == status.HTTP_200_OK


def test_responsible_without_manager_role_can_only_edit_import_title(
    logistics_company, logistics_roles
):
    responsible = CustomUser.objects.create_user(
        email="responsible-reader@example.com",
        password="pass",
    )
    Membership.objects.create(
        user=responsible,
        company=logistics_company,
        role=Role.objects.get_or_create(name="Lecture")[0],
    )
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-TITLE-READER",
        responsable=responsible,
    )
    client = APIClient()
    client.force_authenticate(user=responsible)

    title_response = client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"numero_domiciliation": "TI-OWNER-001"},
        format="json",
    )
    general_response = client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"transport": "Air"},
        format="json",
    )

    assert title_response.status_code == status.HTTP_200_OK
    assert general_response.status_code == status.HTTP_403_FORBIDDEN


def test_partial_payment_keeps_remaining_installment_and_balance(
    api_client,
    logistics_company,
    logistics_user,
    logistics_proformas,
    comptable_user,
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.first()
    assert complete_supplier_proforma_step(api_client, order).status_code == 200
    prepare_valid_import_title(order)
    assert api_client.post(
        reverse("logistique:logistique-request-payment", args=[order.id]),
        payment_schedule_payload(order),
        format="json",
    ).status_code == 200
    installment = order.echeances_paiement.get()
    comptable_client = APIClient()
    comptable_client.force_authenticate(user=comptable_user)

    assert comptable_client.post(
        reverse("logistique:logistique-start-payment", args=[order.id]),
        {"echeance_id": installment.id},
        format="json",
    ).status_code == status.HTTP_200_OK

    execution_response = comptable_client.post(
        reverse("logistique:logistique-record-payment-execution", args=[order.id]),
        payment_execution_payload(installment, montant_paye="150.00"),
        format="json",
    )
    assert execution_response.status_code == status.HTTP_200_OK
    installment.refresh_from_db()
    assert installment.montant_prevu == Decimal("150.00")
    assert order.echeances_paiement.filter(montant_prevu=Decimal("250.00")).exists()

    validation_response = comptable_client.post(
        reverse("logistique:logistique-validate-payment", args=[order.id]),
        payment_validation_payload(installment),
        format="multipart",
    )
    assert validation_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.statut_banque_paiement == "Partiel"
    assert order.solde_restant == Decimal("250.00")
    assert order.paiement_assigne_a == comptable_user

    block_response = comptable_client.post(
        reverse("logistique:logistique-reject-payment", args=[order.id]),
        {"note": "Tentative après paiement partiel"},
        format="json",
    )
    assert block_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    installment.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.statut_banque_paiement == "Partiel"
    assert installment.paiement_valide_le is not None
    assert installment.justificatif_file
    assert order.echeances_paiement.count() == 2


def test_accounting_can_block_for_correction_and_owner_can_resubmit(
    api_client, logistics_company, logistics_user, logistics_proformas, comptable_user
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.first()
    assert complete_supplier_proforma_step(api_client, order).status_code == 200
    prepare_valid_import_title(order)
    request_url = reverse("logistique:logistique-request-payment", args=[order.id])
    assert api_client.post(
        request_url, payment_schedule_payload(order), format="json"
    ).status_code == 200
    comptable_client = APIClient()
    comptable_client.force_authenticate(user=comptable_user)

    block_response = comptable_client.post(
        reverse("logistique:logistique-reject-payment", args=[order.id]),
        {"note": "Référence du titre à corriger"},
        format="json",
    )
    assert block_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_paiement == "Non demandé"
    assert order.statut_banque_paiement == "Bloqué"
    assert order.statut_titre_importation == "À préparer"
    assert order.paiement_assigne_a is None

    edit_response = api_client.put(
        reverse("logistique:logistique-detail", args=[order.id]),
        {"numero_domiciliation": "TI-2026-CORRIGE"},
        format="json",
    )
    assert edit_response.status_code == status.HTTP_200_OK
    resubmit_response = api_client.post(
        request_url, payment_schedule_payload(order), format="json"
    )
    assert resubmit_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.paiement_assigne_a == comptable_user


def test_logistics_admin_keeps_supplier_snapshot_readonly(logistics_company):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-SUPPLIER-ADMIN",
        fournisseur="Supplier One",
    )
    model_admin = LogisticsOrderAdmin(LogisticsOrder, AdminSite())

    readonly_fields = model_admin.get_readonly_fields(None, order)
    assert "fournisseur" in readonly_fields
    assert "statut_paiement" in readonly_fields
    assert "paiement_assigne_a" in readonly_fields

    order.statut_paiement = "En attente"
    assert "titre_importation_file" in model_admin.get_readonly_fields(None, order)


def test_legacy_payment_data_migration_preserves_currency_and_proof(
    logistics_company, logistics_user, comptable_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LEGACY-MIGRATION",
        statut="Paiement effectué",
        statut_paiement="Validé",
        montant_titre_importation=Decimal("100.00"),
        devise_titre_importation="EUR",
        devise_paiement="MAD",
        montant_paiement=Decimal("100.00"),
        date_paiement=timezone.localdate(),
        paiement_valide_le=timezone.now(),
        paiement_valide_par=logistics_user,
        swift_file=SimpleUploadedFile(
            "legacy-swift.pdf",
            b"%PDF-1.4 legacy swift",
            content_type="application/pdf",
        ),
    )
    pending_order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LEGACY-PENDING",
        statut="Paiement demandé",
        statut_paiement="En attente",
        montant_titre_importation=Decimal("50.00"),
        devise_titre_importation="USD",
        devise_paiement="MAD",
        date_titre_importation=timezone.localdate(),
    )
    migration = importlib.import_module(
        "logistique.migrations.0006_historicallogisticsorder_paiement_assigne_a_and_more"
    )

    from django.apps import apps

    migration.migrate_legacy_payment_workflow(apps, None)

    order.refresh_from_db()
    installment = order.echeances_paiement.get()
    assert order.devise_paiement == "EUR"
    assert order.statut_banque_paiement == "Exécuté"
    assert installment.devise == "EUR"
    assert installment.montant_paye == Decimal("100.00")
    assert installment.justificatif_file.name == order.swift_file.name
    pending_order.refresh_from_db()
    pending_installment = pending_order.echeances_paiement.get()
    assert pending_order.devise_paiement == "USD"
    assert pending_order.paiement_assigne_a == comptable_user
    assert pending_installment.devise == "USD"
    assert pending_installment.montant_prevu == Decimal("50.00")
    assert pending_order.history.latest().paiement_assigne_a_id is None


def test_email_delivery_data_migration_preserves_legacy_actions_and_known_address(
    logistics_company, logistics_user, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    sent_at = timezone.now()
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-EMAIL-MIGRATION",
        fournisseur=proforma.fournisseur,
        demande_paiement_envoyee_le=sent_at,
        demande_paiement_envoyee_par=logistics_user,
    )
    LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        devise="EUR",
        preuve_envoyee_fournisseur_le=sent_at,
    )
    migration = importlib.import_module(
        "logistique.migrations.0007_historicallogisticsorder_demande_paiement_email_destinataires_and_more"
    )

    from django.apps import apps

    migration.preserve_legacy_delivery_records(apps, None)

    order.refresh_from_db()
    installment.refresh_from_db()
    assert order.fournisseur_email == "supplier@example.com"
    assert order.demande_paiement_email_statut == "Historique non vérifié"
    assert installment.preuve_email_statut == "Historique non vérifié"
    assert order.history.latest().demande_paiement_email_statut == "Non demandé"


def test_queue_token_migration_makes_preexisting_pending_rows_retryable(
    logistics_company, logistics_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-PRE-TOKEN-PENDING",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_task_id="old-task",
        demande_paiement_email_prise_en_charge_le=timezone.now(),
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        devise="EUR",
        preuve_email_statut="En attente",
        preuve_email_task_id="old-proof-task",
        preuve_email_prise_en_charge_le=timezone.now(),
    )
    migration = importlib.import_module(
        "logistique.migrations.0009_historicallogisticsorder_demande_paiement_email_file_token_and_more"
    )

    from django.apps import apps

    migration.make_pre_token_queued_deliveries_retryable(apps, None)

    order.refresh_from_db()
    installment.refresh_from_db()
    assert order.demande_paiement_email_statut == "Échec"
    assert order.demande_paiement_email_relance_disponible is True
    assert order.demande_paiement_email_task_id == ""
    assert installment.preuve_email_statut == "Échec"
    assert installment.preuve_email_relance_disponible is True
    assert installment.preuve_email_task_id == ""


def test_payment_request_cannot_be_replayed_or_reopen_completed_state(
    api_client, logistics_company, logistics_user, logistics_proformas, comptable_user
):
    create_logistics_order(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    order = LogisticsOrder.objects.first()
    assert (
        complete_supplier_proforma_step(api_client, order).status_code
        == status.HTTP_200_OK
    )
    prepare_valid_import_title(order)
    request_url = reverse("logistique:logistique-request-payment", args=[order.id])

    schedule_payload = payment_schedule_payload(order)
    first_response = api_client.post(request_url, schedule_payload, format="json")
    duplicate_response = api_client.post(request_url, schedule_payload, format="json")

    assert first_response.status_code == status.HTTP_200_OK, first_response.data
    assert duplicate_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.events.filter(action="Demande de paiement").count() == 1

    order.statut_paiement = "Validé"
    order.save(update_fields=["statut_paiement"])
    completed_response = api_client.post(request_url, schedule_payload, format="json")

    assert completed_response.status_code == status.HTTP_400_BAD_REQUEST
    order.refresh_from_db()
    assert order.statut_paiement == "Validé"
    assert order.events.filter(action="Demande de paiement").count() == 1


def test_supplier_proof_email_requires_source_address(
    api_client, logistics_company, logistics_user
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-SUP-EMAIL-REQ",
        fournisseur="Supplier without email",
        responsable=logistics_user,
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        montant_paye=Decimal("100.00"),
        devise="EUR",
        paiement_valide_le=timezone.now(),
        justificatif_file=SimpleUploadedFile(
            "proof.pdf", b"%PDF-1.4 proof", content_type="application/pdf"
        ),
    )

    response = api_client.post(
        reverse("logistique:logistique-send-swift", args=[order.id]),
        {"echeance_id": installment.id},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "fournisseur_email" in response.data["details"]
    installment.refresh_from_db()
    assert installment.preuve_email_statut == "Non demandé"


def test_failed_accounting_email_can_be_requeued_by_order_responsible(
    api_client,
    logistics_company,
    logistics_user,
    django_capture_on_commit_callbacks,
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-ACC-EMAIL-RETRY",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_destinataires=["comptable@example.com"],
        demande_paiement_email_file_token="broker-token",
        demande_paiement_email_mis_en_file_le=timezone.now(),
    )
    from .tasks import deliver_accounting_payment_email, queue_accounting_payment_email

    with patch.object(
        deliver_accounting_payment_email,
        "delay",
        side_effect=RuntimeError("broker unavailable"),
    ):
        queue_accounting_payment_email(order.id, "broker-token")
    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "Échec"
    assert "broker unavailable" in order.demande_paiement_email_erreur

    with patch.object(deliver_accounting_payment_email, "delay") as delay_mock:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                reverse("logistique:logistique-retry-payment-email", args=[order.id]),
                {},
                format="json",
            )

    assert response.status_code == status.HTTP_200_OK
    delay_mock.assert_called_once_with(order.id, ANY)
    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "En attente"
    assert order.demande_paiement_email_erreur == ""


def test_unverified_legacy_supplier_action_must_be_resent_before_confirmation(
    api_client, logistics_company, logistics_user
):
    sent_at = timezone.now() - timedelta(days=1)
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-LEGACY-UNVERIFIED",
        fournisseur="Legacy Supplier",
        fournisseur_email="legacy@example.com",
        responsable=logistics_user,
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        montant_paye=Decimal("100.00"),
        devise="EUR",
        paiement_valide_le=sent_at,
        preuve_email_statut="Historique non vérifié",
        preuve_envoyee_fournisseur_le=sent_at,
        justificatif_file=SimpleUploadedFile(
            "legacy-proof.pdf", b"%PDF-1.4 legacy", content_type="application/pdf"
        ),
    )

    response = api_client.post(
        reverse("logistique:logistique-confirm-payment-receipt", args=[order.id]),
        {"echeance_id": installment.id},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    installment.refresh_from_db()
    assert installment.reception_confirmee_le is None


def test_stale_accounting_email_claim_can_be_requeued(
    api_client,
    logistics_company,
    logistics_user,
    django_capture_on_commit_callbacks,
):
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-STALE-EMAIL",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="Envoi en cours",
        demande_paiement_email_task_id="lost-worker",
        demande_paiement_email_prise_en_charge_le=(
            timezone.now() - LogisticsOrder.EMAIL_DELIVERY_CLAIM_TIMEOUT - timedelta(seconds=1)
        ),
    )
    from .tasks import deliver_accounting_payment_email

    with patch.object(deliver_accounting_payment_email, "delay") as delay_mock:
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(
                reverse("logistique:logistique-retry-payment-email", args=[order.id]),
                {},
                format="json",
            )

    assert response.status_code == status.HTTP_200_OK
    delay_mock.assert_called_once_with(order.id, ANY)
    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "En attente"
    assert order.demande_paiement_email_task_id == ""
    assert order.demande_paiement_email_prise_en_charge_le is None


def test_accounting_delivery_storage_failure_is_retryable_and_refreshes_recipients(
    logistics_company, logistics_user, comptable_user
):
    from .tasks import deliver_accounting_payment_email

    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-STORAGE-FAIL",
        fournisseur="Supplier",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_destinataires=["stale@example.com"],
        demande_paiement_email_file_token="accounting-token",
        demande_paiement_email_mis_en_file_le=timezone.now(),
        proforma_fournisseur_file=SimpleUploadedFile(
            "supplier.pdf", b"%PDF-1.4 supplier", content_type="application/pdf"
        ),
    )

    with patch("logistique.tasks._attach_file", side_effect=OSError("storage unavailable")):
        with pytest.raises(OSError, match="storage unavailable"):
            deliver_accounting_payment_email.run(order.id, "accounting-token")

    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "Échec"
    assert order.demande_paiement_email_destinataires == [comptable_user.email]
    assert "storage unavailable" in order.demande_paiement_email_erreur
    assert deliver_accounting_payment_email.acks_late is True
    assert deliver_accounting_payment_email.reject_on_worker_lost is True


def test_supplier_delivery_storage_failure_is_retryable(
    logistics_company, logistics_user
):
    from .tasks import deliver_supplier_payment_proof_email

    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-SUP-STORAGE-FAIL",
        fournisseur="Supplier",
        fournisseur_email="current-supplier@example.com",
        responsable=logistics_user,
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        montant_paye=Decimal("100.00"),
        devise="EUR",
        paiement_valide_le=timezone.now(),
        preuve_email_statut="En attente",
        preuve_email_destinataire="stale-supplier@example.com",
        preuve_email_file_token="supplier-token",
        preuve_email_mise_en_file_le=timezone.now(),
        justificatif_file=SimpleUploadedFile(
            "proof.pdf", b"%PDF-1.4 proof", content_type="application/pdf"
        ),
    )

    with patch("logistique.tasks._attach_file", side_effect=OSError("storage unavailable")):
        with pytest.raises(OSError, match="storage unavailable"):
            deliver_supplier_payment_proof_email.run(installment.id, "supplier-token")

    installment.refresh_from_db()
    assert installment.preuve_email_statut == "Échec"
    assert installment.preuve_email_destinataire == "current-supplier@example.com"
    assert "storage unavailable" in installment.preuve_email_erreur
    assert deliver_supplier_payment_proof_email.acks_late is True
    assert deliver_supplier_payment_proof_email.reject_on_worker_lost is True


def test_publish_failure_cannot_clobber_a_live_delivery_claim(
    logistics_company, logistics_user
):
    from .tasks import deliver_accounting_payment_email, queue_accounting_payment_email

    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-PUBLISH-RACE",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="Envoi en cours",
        demande_paiement_email_file_token="race-token",
        demande_paiement_email_task_id="worker-task",
        demande_paiement_email_prise_en_charge_le=timezone.now(),
    )

    with patch.object(
        deliver_accounting_payment_email,
        "delay",
        side_effect=RuntimeError("ambiguous publish failure"),
    ):
        queue_accounting_payment_email(order.id, "race-token")

    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "Envoi en cours"
    assert order.demande_paiement_email_task_id == "worker-task"


def test_fresh_delivery_lease_is_never_reclaimed_from_same_task_id(
    logistics_company, logistics_user
):
    from .tasks import _claim_accounting_delivery

    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-FRESH-LEASE",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="Envoi en cours",
        demande_paiement_email_file_token="lease-token",
        demande_paiement_email_task_id="same-task",
        demande_paiement_email_prise_en_charge_le=timezone.now(),
    )

    claimed = _claim_accounting_delivery(order.id, "lease-token", "same-task")

    assert claimed is None
    order.refresh_from_db()
    assert order.demande_paiement_email_tentatives == 0


def test_delivery_claim_revalidates_current_business_state(
    logistics_company, logistics_user
):
    from .tasks import _claim_accounting_delivery

    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-INVALID-CLAIM",
        responsable=logistics_user,
        statut_paiement="Non demandé",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_file_token="invalid-token",
        demande_paiement_email_mis_en_file_le=timezone.now(),
    )

    claimed = _claim_accounting_delivery(order.id, "invalid-token", "worker-task")

    assert claimed is None
    order.refresh_from_db()
    assert order.demande_paiement_email_statut == "Échec"
    assert order.demande_paiement_email_file_token == ""


def test_orphaned_queued_deliveries_become_retryable(
    logistics_company, logistics_user
):
    queued_at = (
        timezone.now() - LogisticsOrder.EMAIL_DELIVERY_CLAIM_TIMEOUT - timedelta(seconds=1)
    )
    order = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-ORPHANED-QUEUE",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_mis_en_file_le=queued_at,
    )
    installment = LogisticsPaymentInstallment.objects.create(
        commande=order,
        date_echeance=timezone.localdate(),
        montant_prevu=Decimal("100.00"),
        devise="EUR",
        preuve_email_statut="En attente",
        preuve_email_mise_en_file_le=queued_at,
    )

    assert order.demande_paiement_email_relance_disponible is True
    assert installment.preuve_email_relance_disponible is True


def test_cancellation_invalidates_queued_email_and_blocks_live_delivery(
    api_client, logistics_company, logistics_user
):
    queued = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-CANCEL-QUEUED",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="En attente",
        demande_paiement_email_file_token="cancel-token",
        demande_paiement_email_mis_en_file_le=timezone.now(),
    )
    queued_response = api_client.patch(
        reverse("logistique:logistique-global-status-update", args=[queued.id]),
        {"statut": "Annulé"},
        format="json",
    )
    queued.refresh_from_db()
    assert queued_response.status_code == status.HTTP_200_OK
    assert queued.demande_paiement_email_statut == "Échec"
    assert queued.demande_paiement_email_file_token == ""

    live = LogisticsOrder.objects.create(
        company=logistics_company,
        numero_commande="LOG-CANCEL-LIVE",
        responsable=logistics_user,
        statut_paiement="En attente",
        demande_paiement_email_statut="Envoi en cours",
        demande_paiement_email_file_token="live-token",
        demande_paiement_email_task_id="live-task",
        demande_paiement_email_prise_en_charge_le=timezone.now(),
    )
    live_response = api_client.patch(
        reverse("logistique:logistique-global-status-update", args=[live.id]),
        {"statut": "Annulé"},
        format="json",
    )
    live.refresh_from_db()
    assert live_response.status_code == status.HTTP_400_BAD_REQUEST
    assert live.statut_global != "Annulé"
    assert live.demande_paiement_email_statut == "Envoi en cours"


def test_logistics_responsible_options_are_company_scoped(
    api_client, logistics_company, logistics_user
):
    url = reverse("logistique:logistique-responsables")

    response = api_client.get(url, {"company_id": logistics_company.id})

    assert response.status_code == status.HTTP_200_OK
    assert response.data == [
        {
            "id": logistics_user.id,
            "first_name": "Log",
            "last_name": "User",
            "email": "logistics@example.com",
            "role": "Caissier",
            "label": "Log User - Caissier",
        }
    ]
