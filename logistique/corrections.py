"""Approval of edits to completed supplier dossier stages."""
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from notification.models import Notification
from .models import LogisticsChangeRequest
from .purchase import purchase_steps
from .historical import historical_steps


def workflow_steps(order):
    return purchase_steps(order) if order.is_supplier_purchase else historical_steps(order)


PROGRESS_FIELDS = {
    "production": {"date_expedition_prevue", "confirmer_production"},
    "expedition": {"date_expedition_reelle", "transport", "documents_originaux_requis", "statut_documents_originaux", "documents_originaux_file"},
    "transit": {"date_arrivee_maroc", "documents_remis_banque_le", "cout_transport", "frais_transit", "frais_douane", "tva"},
    "reception": {"date_reelle"},
    "couts": {"cout_transport", "frais_transit", "frais_douane", "tva", "livraison_locale", "autres_frais"},
}


def notify(order, user, title, message, step):
    Notification.objects.create(user=user, title=title, message=message,
        notification_type="status_change", object_id=order.pk,
        target_url=f"/dashboard/logistique/{order.pk}?company_id={order.company_id}&etape={step}")


def handle_change_request(order, request, *, apply_action=None):
    action = request.data["action"]
    if action == "demander_modification":
        step = serializers.CharField(max_length=30).run_validation(request.data.get("etape"))
        remark = serializers.CharField(max_length=4000, allow_blank=False).run_validation(request.data.get("remarque"))
        steps, current = workflow_steps(order)
        selected = next((item for item in steps if item["key"] == step), None)
        if not selected or not selected["completed"] or not selected["accessible"] or step == current:
            raise ValidationError({"etape": "Seule une étape terminée peut faire l’objet d’une demande de modification."})
        if not order.responsable_id or not order.responsable.is_active:
            raise ValidationError({"responsable": "Affectez un responsable actif au dossier."})
        if "modifications" not in request.data:
            raise ValidationError({"modifications": "Modifiez les champs de l’étape et expliquez le motif avant de soumettre votre proposition."})
        item = order.change_requests.select_for_update().filter(etape=step,
            demandeur=request.user, statut__in=["pending", "approved"]).first()
        if item and (item.statut != "pending" or item.proposed_data):
            raise ValidationError({"demande": "Une demande est déjà en cours pour cette étape."})
        if item:
            item.remarque = remark
            item.save(update_fields=["remarque"])
        else:
            item = LogisticsChangeRequest.objects.create(commande=order, etape=step, remarque=remark,
                demandeur=request.user, responsable=order.responsable)
        from .proposals import prepare_proposal
        prepare_proposal(order, item, request, apply_action)
        from account.models import Membership
        recipients = {order.responsable_id: order.responsable}
        for membership in Membership.objects.filter(company_id=order.company_id,
            role__name="Caissier", user__is_active=True).select_related("user"):
            recipients[membership.user_id] = membership.user
        for recipient in recipients.values():
            notify(order, recipient, "Modification logistique à approuver",
                f"Dossier {order.numero_commande} · {selected['label']} : {remark}", step)
        order.add_event(user=request.user, action="Modification d’une étape demandée", new_value=selected["label"], note=remark)
        return item
    identifier = serializers.IntegerField(min_value=1).run_validation(request.data.get("demande_id"))
    item = order.change_requests.select_for_update().filter(pk=identifier, statut="pending").first()
    if not item:
        raise ValidationError({"demande_id": "Demande en attente introuvable."})
    from core.permissions import is_caissier
    if request.user.pk != order.responsable_id and not is_caissier(request.user, order.company_id):
        raise PermissionDenied("Seul le responsable ou un administrateur de la société peut décider de cette demande.")
    accepted = action == "approuver_modification"
    if accepted and not item.proposed_data:
        raise ValidationError({"modifications": "Le demandeur doit renseigner les valeurs à modifier avant la validation."})
    if accepted and item.proposed_data:
        from .proposals import apply_proposal
        apply_proposal(order, item, request, apply_action)
        item.refresh_from_db()
    else:
        item.statut = "approved" if accepted else "rejected"
    item.responsable = request.user
    item.decided_at = timezone.now()
    item.save(update_fields=["responsable", "statut", "decided_at"])
    label = "approuvée" if accepted else "refusée"
    notify(order, item.demandeur, f"Modification logistique {label}",
        f"Votre demande pour le dossier {order.numero_commande} a été {label}.", item.etape)
    order.add_event(user=request.user, action=f"Demande de modification {label}", new_value=item.etape, note=item.remarque)
    return item


def authorize_step(order, request, step):
    steps, current = workflow_steps(order)
    selected = next((item for item in steps if item["key"] == step), None)
    if not selected or not selected["accessible"]:
        raise ValidationError({"etape": "Terminez l’étape en cours avant de poursuivre."})
    if step == current:
        return None
    identifier = request.data.get("correction_id")
    if not identifier:
        raise PermissionDenied("Cette étape est en lecture seule. Demandez une modification au responsable.")
    identifier = serializers.IntegerField(min_value=1).run_validation(identifier)
    approval = order.change_requests.select_for_update().filter(pk=identifier,
        etape=step, demandeur=request.user, statut="approved").first()
    if not approval:
        raise PermissionDenied("Aucune autorisation de modification valide pour cette étape.")
    return approval


def action_step(order, data):
    action = data.get("action")
    if action == "corriger_paiement":
        step = data.get("etape")
        if step not in {"paiement", "solde"}:
            raise ValidationError({"etape": "Choisissez l’étape du paiement à corriger."})
        return step
    if action == "corriger_reception":
        return "reception"
    if action in {"dossier", "proforma", "titre", "reception"}:
        return action
    if action != "progression":
        return None
    step = data.get("etape")
    supplied = set(data) - {"action", "etape", "correction_id", "remarque", "statut", "justificatifs_file"}
    if not step:
        step = next((key for key, fields in PROGRESS_FIELDS.items() if supplied and supplied <= fields), None)
        if not step and not supplied:
            step = {"Production": "production", "Expédition": "expedition", "Transit": "transit",
                "Dédouanement": "transit", "Réception locale": "reception", "Livraison client": "reception", "Clôture": "couts"}.get(data.get("statut"))
            if not step and not data.get("statut"):
                return None
    if step not in PROGRESS_FIELDS or supplied - PROGRESS_FIELDS[step]:
        raise ValidationError({"etape": "Modifiez uniquement les champs de l’étape sélectionnée."})
    targets = {"production": {"Production"}, "expedition": {"Expédition"},
        "transit": {"Transit", "Dédouanement"}, "reception": {"Réception locale", "Livraison client"}, "couts": {"Clôture"}}
    if data.get("statut") and data["statut"] not in targets[step] | {order.statut}:
        raise ValidationError({"statut": "Cette phase ne correspond pas à l’étape sélectionnée."})
    return step


def consume_approval(order, approval, user):
    if approval:
        approval.statut = "applied"
        approval.applied_at = timezone.now()
        approval.save(update_fields=["statut", "applied_at"])
        order.add_event(user=user, action="Correction autorisée enregistrée", new_value=approval.etape, note=approval.remarque)
