"""Supplier dossier operations shared by saves and approved corrections."""

import json
from copy import copy
from typing import Any, cast

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from article.models import Article
from company.models import Company
from parameter.models import Marque
from stock.models import StockReceipt, StockReceiptLine
from stock.serializers import StockReceiptSerializer
from stock.services import activate_incoming, validate_receipt

from .compatibility import can_adopt_supplier_workflow, json_snapshot
from .corrections import consume_approval
from .historical_services import apply_historical_correction
from .history import business_snapshot, record_business_changes
from .models import LogisticsOrder, LogisticsOrderLine, LogisticsProcessNote
from .purchase import (
    CONDITIONS,
    create_purchase_schedule,
    payment_blocker,
    preparation_blocker,
    validate_purchase_transition,
)
from .purchase_serializers import (
    PurchaseDossierSerializer,
    PurchasePaymentRequestSerializer,
    PurchaseProformaSerializer,
    PurchaseProgressSerializer,
)
from .selectors import get_order
from .serializers import LOGISTICS_IMPORT_TITLE_FIELDS, LogisticsOrderUpdateSerializer
from .services import (
    assign_payment_task,
    clear_payment_installment_cache,
    get_locked_installment,
    send_payment_request_email,
)
from .suppliers import ensure_supplier
from .tasks import queue_purchase_creator_email
from .utils import get_next_numero_logistique


def create_purchase_dossier(company_id, user, data):
    serializer = PurchaseDossierSerializer(
        data=data, context={"company_id": company_id, "create": True}
    )
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data.copy()
    supplier = values.pop("fournisseur_record", None)
    brand_id = values.pop("marque", None)
    responsible_id = values.pop("responsable", None) or user.pk
    brand: Marque | None = (
        Marque.objects.filter(pk=brand_id, company_id=company_id).first()
        if brand_id
        else None
    )
    if "fournisseur_email" not in values and brand is not None:
        values["fournisseur_email"] = brand.email
    with transaction.atomic():
        # Number allocation also locks the company when no dossier exists yet.
        Company.objects.select_for_update().get(pk=company_id)
        supplier = supplier or ensure_supplier(
            company_id, values["fournisseur"], values.get("fournisseur_email", "")
        )
        if brand:
            supplier.marques.add(brand)
        order = LogisticsOrder.objects.create(
            company_id=company_id,
            fournisseur_record=supplier,
            numero_commande=get_next_numero_logistique(company_id),
            workflow_version=2,
            responsable_id=responsible_id,
            marque=brand,
            created_by_user=user,
            statut_commande_lancement="Terminée",
            statut="Proforma",
            statut_global="En attente externe",
            **values,
        )
        order.add_event(
            user=user,
            action="Création du dossier fournisseur",
            new_value=order.numero_commande,
        )
    return [order]


def apply_purchase_action(order, request, approval):
    """Apply the same validated business operation for direct saves and accepted proposals."""
    pk = order.pk
    if not order.is_supplier_purchase:
        return apply_historical_correction(order, request, approval)
    if (
        order.statut == "Clôture"
        and request.data.get("action") != "relancer_notification"
    ):
        raise ValidationError({"dossier": "Ce dossier est clôturé."})
    action = request.data.get("action")
    if set(request.data) == {"action"} and action in {
        "dossier",
        "titre",
        "progression",
    }:
        return order
    decision = ""
    before = (
        business_snapshot(order, include_lines=action == "proforma")
        if action in {"dossier", "proforma", "titre", "progression"}
        else None
    )
    if action == "dossier":
        serializer = PurchaseDossierSerializer(
            data=request.data, context={"company_id": order.company_id, "order": order}
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        supplier = values.pop("fournisseur_record", None)
        old_name = order.fournisseur
        for field, value in values.items():
            setattr(
                order,
                {"responsable": "responsable_id", "marque": "marque_id"}.get(
                    field, field
                ),
                value,
            )
        if supplier:
            order.fournisseur_record = supplier
        elif order.fournisseur != old_name or not order.fournisseur_record_id:
            order.fournisseur_record = ensure_supplier(
                order.company_id, order.fournisseur, order.fournisseur_email
            )
            if order.marque_id:
                order.fournisseur_record.marques.add(order.marque_id)
        order.save()
    elif action == "proforma":
        if order.is_proforma_step_complete and not approval:
            raise ValidationError(
                {"proforma": "La proforma fournisseur est déjà validée."}
            )
        if (
            order.legacy_source_snapshot
            and order.lignes.filter(
                Q(proforma__isnull=False)
                | Q(source_line__isnull=False)
                | Q(client__isnull=False)
            ).exists()
            and "lignes" not in request.data
        ):
            raise ValidationError(
                {
                    "lignes": (
                        "Renseignez les quantités et prix de la proforma fournisseur. Les "
                        "anciennes lignes client ne sont pas des achats confirmés."
                    )
                }
            )
        data = copy(request.data)
        data["action"] = request.data.get("decision", "validate")
        serializer = PurchaseProformaSerializer(data=data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        decision = cast(str, values.pop("action"))
        lines: list[dict[str, Any]] | None = values.pop("lignes", None)
        if approval and order.is_proforma_step_complete:
            if decision != "validate":
                raise ValidationError(
                    {
                        "decision": "Une correction doit conserver la validation de la proforma."
                    }
                )
            if any(
                values.get(field, getattr(order, field)) != getattr(order, field)
                for field in (
                    "montant_proforma_fournisseur",
                    "devise_proforma_fournisseur",
                    "condition_achat",
                )
            ):
                raise ValidationError(
                    {
                        "proforma": (
                            "Le montant, la devise et les conditions d’une proforma validée restent"
                            " liés à son échéancier comptable."
                        )
                    }
                )
            if lines is not None:
                existing_lines = list(order.lignes.order_by("id"))
                same_lines = len(lines) == len(existing_lines) and all(
                    line["article"] == old.article_id
                    and line["quantity"] == old.quantity
                    and line["prix_achat"] == old.prix_achat
                    and line.get("expected_emplacement", old.expected_emplacement_id)
                    == old.expected_emplacement_id
                    for line, old in zip(lines, existing_lines)
                )
                if not same_lines:
                    raise ValidationError(
                        {
                            "lignes": (
                                "Les articles validés restent liés à l’échéancier et aux réceptions. "
                                "Ils ne peuvent pas être remplacés."
                            )
                        }
                    )
                lines = None
        for field, value in values.items():
            setattr(order, field, value)
        order.devise = order.devise_proforma_fournisseur
        _, advance, method, _ = CONDITIONS[order.condition_achat]
        order.avance_pourcentage = advance
        order.methode_paiement = method
        if lines is not None:
            if StockReceiptLine.objects.filter(logistics_line__commande=order).exists():
                raise ValidationError(
                    {
                        "lignes": "Des réceptions utilisent déjà ces lignes. Elles ne peuvent plus être remplacées."
                    }
                )
            order.lignes.all().delete()
            articles = Article.objects.in_bulk([line["article"] for line in lines])
            for line in lines:
                article = articles[line["article"]]
                LogisticsOrderLine.objects.create(
                    commande=order,
                    article=article,
                    article_reference=article.reference,
                    designation=article.designation,
                    marque_name=str(article.marque) if article.marque_id else "",
                    quantity=line["quantity"],
                    prix_achat=line["prix_achat"],
                    devise_prix_achat=order.devise,
                    expected_emplacement_id=line.get("expected_emplacement")
                    or article.emplacement_id,
                )
        getattr(order, "_prefetched_objects_cache", {}).pop("lignes", None)
        order.statut_proforma_conformite = {
            "control": "En contrôle",
            "request_correction": "Correction demandée",
            "validate": "Validée",
            "reject": "Refusée",
        }[decision]
        order.proforma_controlee_le = timezone.now()
        order.proforma_controlee_par = request.user
        if decision == "validate":
            order.proforma_validee_le = timezone.now()
            order.proforma_validee_par = request.user
            create_purchase_schedule(order)
            getattr(order, "_prefetched_objects_cache", {}).pop(
                "echeances_paiement", None
            )
            activate_incoming(order)
        order.save()
    elif action == "titre":
        allowed = LOGISTICS_IMPORT_TITLE_FIELDS - {
            "date_validation_titre_importation",
            "statut_titre_importation",
            "methode_paiement",
            "avance_pourcentage",
        }
        values = {key: value for key, value in request.data.items() if key in allowed}
        serializer = LogisticsOrderUpdateSerializer(
            order,
            data=values,
            partial=True,
            context={"approved_correction": bool(approval)},
        )
        serializer.is_valid(raise_exception=True)
        if approval and (
            serializer.validated_data.get(
                "montant_titre_importation", order.montant_titre_importation
            )
            != order.payment_total
            or serializer.validated_data.get(
                "devise_titre_importation", order.devise_titre_importation
            )
            != order.devise_proforma_fournisseur
        ):
            raise ValidationError(
                {
                    "titre": "Le montant et la devise doivent correspondre à la proforma validée."
                }
            )
        serializer.save()
    elif action == "progression":
        serializer = PurchaseProgressSerializer(
            data=request.data,
            context={"order": order, "approved_correction": bool(approval)},
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        remark = values.pop("remarque", "").strip()
        confirm = values.pop("confirmer_production", False)
        target = values.pop(
            "statut",
            (
                "Expédition"
                if values.get("date_expedition_reelle")
                and not order.date_expedition_reelle
                else order.statut
            ),
        )
        for field, value in values.items():
            setattr(order, field, value)
        if confirm:
            reason = preparation_blocker(order)
            if reason:
                raise ValidationError({"production": reason})
            order.production_confirmee_le = (
                order.production_confirmee_le or timezone.now()
            )
            target = "Production"
        validate_purchase_transition(order, order.statut if approval else target)
        if not approval:
            order.statut = target
        order.save()
        if remark:
            note = LogisticsProcessNote.objects.create(
                commande=order,
                user=request.user,
                statut=order.statut,
                remarque=(
                    f"Retard d’expédition ({order.date_expedition_prevue}) : " + remark
                    if order.date_expedition_prevue
                    and (order.date_expedition_reelle or timezone.localdate())
                    > order.date_expedition_prevue
                    else remark
                ),
            )
            order.add_event(
                user=request.user,
                action=(
                    "Explication du retard d’expédition"
                    if note.remarque.startswith("Retard d’expédition (")
                    else "Remarque ajoutée au dossier"
                ),
                note=note.remarque,
            )
    elif action == "reception":
        receipt_file = request.FILES.get("bon_reception_file")
        if receipt_file:
            from .serializers import validate_logistics_document

            validate_logistics_document(receipt_file)
        validate_purchase_transition(order, "Expédition", enforce_sequence=False)
        data = {
            "logistics_order": order.pk,
            "reference": request.data.get("reference", ""),
            "note": request.data.get("note", ""),
            "lines": request.data.get("lines", []),
        }
        if isinstance(data["lines"], str):
            try:
                data["lines"] = json.loads(data["lines"])
            except (ValueError, TypeError):
                raise ValidationError(
                    {"lines": "Les lignes de réception sont invalides."}
                )
        serializer = StockReceiptSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        validate_receipt(receipt, request.user)
        if receipt_file:
            order.bon_reception_file = receipt_file
            order.save(update_fields=["bon_reception_file", "date_updated"])
        details = [
            f"Référence : {receipt.reference or f'Réception #{receipt.pk}'}",
            "Quantités reçues :",
        ]
        for line in receipt.lines.select_related(
            "article", "emplacement", "logistics_line"
        ).order_by("id"):
            details.append(
                f"- {line.article.reference} : {line.quantity} ; emplacement {line.emplacement} ; "
                f"total reçu {line.logistics_line.received_quantity} / {line.logistics_line.quantity}"
            )
        if receipt.note:
            details.append(f"Note de réception :\n{receipt.note}")
        order.add_event(
            user=request.user,
            action="Réception de marchandises",
            new_value=(receipt.reference or f"Réception #{receipt.pk}")[:255],
            note="\n".join(details),
        )
        order.refresh_from_db()
    elif action == "corriger_paiement":
        if not approval:
            raise PermissionDenied(
                "Une correction de paiement nécessite une autorisation."
            )
        if set(request.data) - {
            "action",
            "etape",
            "correction_id",
            "echeance_id",
            "reference_paiement",
            "commentaire_paiement",
        }:
            raise ValidationError(
                {
                    "paiement": "Seuls la référence et le commentaire peuvent être corrigés."
                }
            )
        identifier = serializers.IntegerField(min_value=1).run_validation(
            request.data.get("echeance_id")
        )
        item = (
            order.echeances_paiement.select_for_update()
            .filter(pk=identifier, paiement_valide_le__isnull=False)
            .first()
        )
        if (
            not item
            or ("paiement" if item.declencheur == "advance" else "solde")
            != approval.etape
        ):
            raise ValidationError(
                {"echeance_id": "Paiement validé introuvable pour cette étape."}
            )
        reference = serializers.CharField(
            max_length=120, allow_blank=True
        ).run_validation(request.data.get("reference_paiement", ""))
        comment = serializers.CharField(
            max_length=4000, allow_blank=True
        ).run_validation(request.data.get("commentaire_paiement", ""))
        order.add_event(
            user=request.user,
            action="Correction de la référence du paiement",
            old_value=item.reference_bancaire,
            new_value=reference,
            note=comment,
        )
        item.reference_bancaire = reference
        item.commentaire = comment
        item.save(update_fields=["reference_bancaire", "commentaire", "date_updated"])
    elif action == "corriger_reception":
        if not approval:
            raise PermissionDenied(
                "Une correction de réception nécessite une autorisation."
            )
        if set(request.data) - {
            "action",
            "etape",
            "correction_id",
            "reception_id",
            "reference",
            "note",
        }:
            raise ValidationError(
                {
                    "reception": "Seuls la référence et la remarque peuvent être corrigées."
                }
            )
        identifier = serializers.IntegerField(min_value=1).run_validation(
            request.data.get("reception_id")
        )
        receipt = (
            StockReceipt.objects.select_for_update()
            .filter(pk=identifier, logistics_order=order, company_id=order.company_id)
            .first()
        )
        if not receipt:
            raise ValidationError(
                {"reception_id": "Réception introuvable pour ce dossier."}
            )
        reference = serializers.CharField(
            max_length=80, allow_blank=True
        ).run_validation(request.data.get("reference", ""))
        note = serializers.CharField(max_length=4000, allow_blank=True).run_validation(
            request.data.get("note", "")
        )
        order.add_event(
            user=request.user,
            action="Correction des informations de réception",
            old_value=receipt.reference,
            new_value=reference,
            note=f"Ancienne remarque : {receipt.note}\nNouvelle remarque : {note}",
        )
        receipt.reference, receipt.note = reference, note
        receipt.save(update_fields=["reference", "note"])
    elif action == "relancer_notification":
        try:
            item = order.echeances_paiement.get(
                pk=request.data.get("echeance_id"), paiement_valide_le__isnull=False
            )
        except (ValueError, TypeError, order.echeances_paiement.model.DoesNotExist):
            raise ValidationError({"echeance_id": "Paiement validé introuvable."})
        transaction.on_commit(lambda: queue_purchase_creator_email(item.pk))
        order.add_event(
            user=request.user,
            action="Relance de la notification au créateur demandée",
            new_value=f"Paiement de {item.montant_paye:.2f} {item.devise}",
        )
    else:
        raise ValidationError({"action": "Action inconnue."})
    if before is not None:
        recorded = record_business_changes(
            order, before, user=request.user, uploaded_fields=request.FILES
        )
        if action == "proforma" and not recorded:
            description = {
                "control": "Contrôle de la proforma fournisseur enregistré",
                "request_correction": "Correction de la proforma fournisseur demandée",
                "validate": "Proforma fournisseur validée",
                "reject": "Proforma fournisseur refusée",
            }[decision]
            order.add_event(
                user=request.user,
                action=description,
                new_value=order.numero_proforma_fournisseur,
            )
    consume_approval(order, approval, request.user)
    order.sync_global_status(preserve_manual=False)
    # Reload relation caches after changes to avoid returning stale form data.
    return get_order(pk)


def request_purchase_payment(order, request):
    serializer = PurchasePaymentRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item = get_locked_installment(order, serializer.validated_data["echeance_id"])
    if item.demandee_le or item.paiement_valide_le:
        raise ValidationError({"paiement": "Cette échéance a déjà été transmise."})
    reason = payment_blocker(order, item)
    if reason:
        raise ValidationError({"paiement": reason})
    if order.demande_paiement_email_statut in {"En attente", "Envoi en cours"}:
        raise ValidationError(
            {"email": "Attendez la fin de l’envoi de la demande précédente."}
        )
    if not (
        order.numero_domiciliation.strip()
        and order.banque.strip()
        and order.date_titre_importation
        and order.titre_importation_file
    ):
        raise ValidationError(
            {
                "titre": "Renseignez et vérifiez le titre d’importation avant la demande de paiement."
            }
        )
    if (
        order.montant_titre_importation != order.payment_total
        or order.devise_titre_importation != order.devise_proforma_fournisseur
    ):
        raise ValidationError(
            {
                "titre": (
                    "Vérifiez le montant et la devise du titre d’importation : ils doivent "
                    "correspondre à la proforma fournisseur."
                )
            }
        )
    item.date_echeance = serializer.validated_data["date_echeance"]
    item.demandee_le = timezone.now()
    item.save(update_fields=["date_echeance", "demandee_le", "date_updated"])
    clear_payment_installment_cache(order)
    assign_payment_task(order)
    order.date_validation_titre_importation = (
        order.date_validation_titre_importation or timezone.localdate()
    )
    order.statut_titre_importation = "Titre d'import validé – En attente de paiement"
    order.statut_banque_paiement = "En validation"
    order.statut_traitement_paiement = "Paiement à traiter"
    order.save()
    send_payment_request_email(order, request_user=request.user)
    return order


def adopt_supplier_workflow(order, *, user, data):
    """Called only by an explicit POST within the locked purchase transaction."""
    if not can_adopt_supplier_workflow(order):
        raise ValidationError(
            {
                "dossier": "Ce dossier a déjà engagé des opérations. Son parcours historique doit être conservé."
            }
        )
    serializer = PurchaseDossierSerializer(
        data=data, context={"company_id": order.company_id, "create": True}
    )
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data.copy()
    supplier = values.pop("fournisseur_record", None)
    responsible_id = values.pop("responsable", None) or order.responsable_id or user.pk
    # Validate a preserved default with the same active membership rules as an explicit choice.
    defaults = PurchaseDossierSerializer(
        data={"responsable": responsible_id}, context={"company_id": order.company_id}
    )
    defaults.is_valid(raise_exception=True)
    order.legacy_source_snapshot = json_snapshot(order)
    for field, value in values.items():
        setattr(order, "marque_id" if field == "marque" else field, value)
    order.responsable_id = responsible_id
    order.fournisseur_record = supplier or ensure_supplier(
        order.company_id, order.fournisseur, order.fournisseur_email
    )
    order.workflow_version = 2
    order.statut = "Proforma"
    order.statut_commande_lancement = "Terminée"
    order.prochaine_relance_proforma = None
    order.save()
    order.add_event(
        user=user,
        action="Passage au parcours d’achat fournisseur",
        old_value="Dossier issu de proformas client",
        new_value="Dossier d’achat fournisseur",
        note=(
            "Les documents, les liens d’origine et leurs données sont conservés. "
            "Les quantités et prix fournisseur seront renseignés lors du contrôle "
            "de la proforma fournisseur."
        ),
    )
