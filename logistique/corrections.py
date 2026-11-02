"""Approval of edits to completed supplier dossier stages."""

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from account.models import Membership
from core.permissions import is_caissier
from notification.models import Notification

from .historical import historical_steps
from .models import LogisticsChangeRequest
from .proposals import apply_proposal, prepare_proposal
from .purchase import purchase_steps


def workflow_steps(order):
    return (
        purchase_steps(order) if order.is_supplier_purchase else historical_steps(order)
    )


def notify(order, user, title, message, step):
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type="status_change",
        object_id=order.pk,
        target_url=f"/dashboard/logistique/{order.pk}?company_id={order.company_id}&etape={step}",
    )


def handle_change_request(order, request, *, apply_action=None):
    action = request.data["action"]
    if action == "demander_modification":
        step = serializers.CharField(max_length=30).run_validation(
            request.data.get("etape")
        )
        remark = serializers.CharField(
            max_length=4000, allow_blank=False
        ).run_validation(request.data.get("remarque"))
        steps, current = workflow_steps(order)
        selected = next((item for item in steps if item["key"] == step), None)
        if (
            not selected
            or not selected["completed"]
            or not selected["accessible"]
            or step == current
        ):
            raise ValidationError(
                {
                    "etape": "Seule une étape terminée peut faire l’objet d’une demande de modification."
                }
            )
        if not order.responsable_id or not order.responsable.is_active:
            raise ValidationError(
                {"responsable": "Affectez un responsable actif au dossier."}
            )
        if "modifications" not in request.data:
            raise ValidationError(
                {
                    "modifications": "Modifiez les champs de l’étape et expliquez le motif avant de soumettre votre proposition."
                }
            )
        item = (
            order.change_requests.select_for_update()
            .filter(
                etape=step, demandeur=request.user, statut__in=["pending", "approved"]
            )
            .first()
        )
        if item and (item.statut != "pending" or item.proposed_data):
            raise ValidationError(
                {"demande": "Une demande est déjà en cours pour cette étape."}
            )
        if item:
            item.remarque = remark
            item.save(update_fields=["remarque"])
        else:
            item = LogisticsChangeRequest.objects.create(
                commande=order,
                etape=step,
                remarque=remark,
                demandeur=request.user,
                responsable=order.responsable,
            )
        prepare_proposal(order, item, request, apply_action)
        recipients = {order.responsable_id: order.responsable}
        for membership in Membership.objects.filter(
            company_id=order.company_id, role__name="Caissier", user__is_active=True
        ).select_related("user"):
            recipients[membership.user_id] = membership.user
        for recipient in recipients.values():
            notify(
                order,
                recipient,
                "Modification logistique à approuver",
                f"Dossier {order.numero_commande} · {selected['label']} : {remark}",
                step,
            )
        order.add_event(
            user=request.user,
            action="Modification d’une étape demandée",
            new_value=selected["label"],
            note=remark,
        )
        return item
    identifier = serializers.IntegerField(min_value=1).run_validation(
        request.data.get("demande_id")
    )
    item = (
        order.change_requests.select_for_update()
        .filter(pk=identifier, statut="pending")
        .first()
    )
    if not item:
        raise ValidationError({"demande_id": "Demande en attente introuvable."})
    if request.user.pk != order.responsable_id and not is_caissier(
        request.user, order.company_id
    ):
        raise PermissionDenied(
            "Seul le responsable ou un administrateur de la société peut décider de cette demande."
        )
    accepted = action == "approuver_modification"
    if accepted and not item.proposed_data:
        raise ValidationError(
            {
                "modifications": "Le demandeur doit renseigner les valeurs à modifier avant la validation."
            }
        )
    if accepted and item.proposed_data:
        apply_proposal(order, item, request, apply_action)
        item.refresh_from_db()
    else:
        item.statut = "approved" if accepted else "rejected"
    item.responsable = request.user
    item.decided_at = timezone.now()
    item.save(update_fields=["responsable", "statut", "decided_at"])
    label = "approuvée" if accepted else "refusée"
    notify(
        order,
        item.demandeur,
        f"Modification logistique {label}",
        f"Votre demande pour le dossier {order.numero_commande} a été {label}.",
        item.etape,
    )
    order.add_event(
        user=request.user,
        action=f"Demande de modification {label}",
        new_value=item.etape,
        note=item.remarque,
    )
    return item


def authorize_step(order, request, step):
    steps, current = workflow_steps(order)
    selected = next((item for item in steps if item["key"] == step), None)
    if not selected or not selected["accessible"]:
        raise ValidationError(
            {"etape": "Terminez l’étape en cours avant de poursuivre."}
        )
    if step == current:
        return None
    identifier = request.data.get("correction_id")
    if not identifier:
        raise PermissionDenied(
            "Cette étape est en lecture seule. Demandez une modification au responsable."
        )
    identifier = serializers.IntegerField(min_value=1).run_validation(identifier)
    approval = (
        order.change_requests.select_for_update()
        .filter(pk=identifier, etape=step, demandeur=request.user, statut="approved")
        .first()
    )
    if not approval:
        raise PermissionDenied(
            "Aucune autorisation de modification valide pour cette étape."
        )
    return approval


def consume_approval(order, approval, user):
    if approval:
        approval.statut = "applied"
        approval.applied_at = timezone.now()
        approval.save(update_fields=["statut", "applied_at"])
        order.add_event(
            user=user,
            action="Correction autorisée enregistrée",
            new_value=approval.etape,
            note=approval.remarque,
        )
