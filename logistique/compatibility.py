"""Explicit adoption of the supplier workflow for untouched dossiers."""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError


def can_adopt_supplier_workflow(order):
    """Read-only eligibility; rechecked under the order lock when saving."""
    if order.workflow_version != 1 or order.legacy_source_snapshot:
        return False
    if order.statut not in {"Réception commande", "Proforma"} or order.statut_global in {"Annulé", "Clôturé"}:
        return False
    if (order.statut_proforma_conformite == "Validée" or order.is_proforma_step_complete
            or order.proforma_validee_le or order.proforma_validee_par_id):
        return False
    if order.statut_paiement != "Non demandé" or order.statut_banque_paiement != "À préparer":
        return False
    if order.statut_traitement_paiement != "Paiement à traiter" or order.statut_titre_importation != "À préparer":
        return False
    completed_fields = (
        "date_validation_titre_importation", "paiement_assigne_a_id",
        "demande_paiement_envoyee_le", "demande_paiement_envoyee_par_id",
        "demande_paiement_email_destinataires", "demande_paiement_email_erreur",
        "demande_paiement_email_tentatives", "demande_paiement_email_task_id",
        "demande_paiement_email_file_token", "demande_paiement_email_mis_en_file_le",
        "demande_paiement_email_prise_en_charge_le", "paiement_valide_le", "paiement_valide_par_id",
        "date_paiement", "montant_paiement", "banque_paiement", "reference_paiement",
        "commentaire_paiement", "date_upload_swift", "swift_file",
        "swift_envoye_fournisseur_le", "paiement_confirme_reception_le", "paiement_confirme_reception_par_id",
        "production_confirmee_le", "date_expedition_reelle", "date_arrivee_maroc",
        "documents_remis_banque_le", "date_reelle", "condition_achat",
        "cout_transport", "frais_transit", "frais_douane", "tva", "livraison_locale", "autres_frais",
    )
    if any(getattr(order, field) for field in completed_fields):
        return False
    if order.demande_paiement_email_statut != "Non demandé":
        return False
    if order.echeances_paiement.exists() or order.stock_receipts.exists():
        return False
    if order.lignes.filter(received_quantity__gt=0).exists():
        return False
    from stock.models import StockMovement
    return not StockMovement.objects.filter(
        Q(source_type="LogisticsOrder", source_id=order.pk)
        | Q(source_type="LogisticsOrderLine", source_line_id__in=order.lignes.values("pk"))
    ).exists()


def _json_snapshot(order):
    fields = {}
    for field in order._meta.concrete_fields:
        if field.name == "legacy_source_snapshot":
            continue
        value = getattr(order, field.attname)
        fields[field.attname] = str(value) if field.get_internal_type() == "FileField" else value
    snapshot = {
        "archived_at": timezone.now(),
        "order": fields,
        "lines": list(order.lignes.order_by("pk").values()),
        "proforma_links": list(order.proformas.through.objects.filter(commande_id=order.pk).order_by("pk").values()),
        "brand_ids": list(order.marques.order_by("pk").values_list("pk", flat=True)),
    }
    return json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))


def adopt_supplier_workflow(order, *, user, data):
    """Called only by an explicit POST within the locked purchase transaction."""
    if not can_adopt_supplier_workflow(order):
        raise ValidationError({"dossier": "Ce dossier a déjà engagé des opérations. Son parcours historique doit être conservé."})
    from .purchase_serializers import PurchaseDossierSerializer
    from .suppliers import ensure_supplier
    serializer = PurchaseDossierSerializer(data=data, context={"company_id": order.company_id, "create": True})
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data.copy()
    supplier = values.pop("fournisseur_record", None)
    responsible_id = values.pop("responsable", None) or order.responsable_id or user.pk
    # Validate a preserved default with the same active membership rules as an explicit choice.
    defaults = PurchaseDossierSerializer(data={"responsable": responsible_id}, context={"company_id": order.company_id})
    defaults.is_valid(raise_exception=True)
    order.legacy_source_snapshot = _json_snapshot(order)
    for field, value in values.items():
        setattr(order, "marque_id" if field == "marque" else field, value)
    order.responsable_id = responsible_id
    order.fournisseur_record = supplier or ensure_supplier(order.company_id, order.fournisseur, order.fournisseur_email)
    order.workflow_version = 2
    order.statut = "Proforma"
    order.statut_commande_lancement = "Terminée"
    order.prochaine_relance_proforma = None
    order.save()
    order.add_event(user=user, action="Passage au parcours d’achat fournisseur",
        old_value="Dossier issu de proformas client", new_value="Dossier d’achat fournisseur",
        note="Les documents, les liens d’origine et leurs données sont conservés. Les quantités et prix fournisseur seront renseignés lors du contrôle de la proforma fournisseur.")
