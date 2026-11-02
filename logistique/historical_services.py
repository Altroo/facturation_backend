"""Validated edits to dossiers that retain the customer-proforma workflow."""

from rest_framework.exceptions import ValidationError

from .corrections import authorize_step, consume_approval
from .historical import EDIT_FIELDS, historical_steps
from .selectors import get_order
from .serializers import LogisticsOrderUpdateSerializer


def authorize_historical_edit(order, request):
    _, current = historical_steps(order)
    selected = request.data.get("etape", current)
    approval = authorize_step(order, request, selected)
    allowed = EDIT_FIELDS.get(selected, set()) | {"etape", "correction_id"}
    if selected == current:
        allowed |= {"statut"}
    if set(request.data) - allowed:
        raise ValidationError(
            {"etape": "Modifiez uniquement les champs de l’étape sélectionnée."}
        )
    target = request.data.get("statut", order.statut)
    if target != order.statut:
        targets = {
            "paiement": {"Production"} if order.is_payment_step_complete else set(),
            "production": {"Expédition"},
            "expedition": {"Transit"},
            "transit": {"Dédouanement", "Réception locale"},
            "reception": {"Livraison client"},
            "couts": {"Clôture"},
        }
        if target not in targets.get(current, set()):
            raise ValidationError(
                {"statut": "Terminez l’étape en cours avant de poursuivre."}
            )
    if approval and selected == "paiement":
        # A reference correction must not change the validated accounting schedule.
        for field in (
            "montant_titre_importation",
            "devise_titre_importation",
            "methode_paiement",
            "avance_pourcentage",
        ):
            if field in request.data and str(request.data[field]) != str(
                getattr(order, field)
            ):
                raise ValidationError(
                    {field: "Cette valeur reste liée au paiement comptabilisé."}
                )
    return approval


def apply_historical_correction(order, request, approval):
    allowed = EDIT_FIELDS.get(approval.etape, set()) | {
        "action",
        "etape",
        "correction_id",
    }
    if set(request.data) - allowed:
        raise ValidationError(
            {"etape": "Modifiez uniquement les champs de l’étape sélectionnée."}
        )
    serializer = LogisticsOrderUpdateSerializer(
        order,
        data=request.data,
        partial=True,
        context={"request": request, "approved_correction": True},
    )
    serializer.is_valid(raise_exception=True)
    if approval.etape == "paiement":
        for field in (
            "montant_titre_importation",
            "devise_titre_importation",
            "methode_paiement",
            "avance_pourcentage",
        ):
            if field in serializer.validated_data and serializer.validated_data[
                field
            ] != getattr(order, field):
                raise ValidationError(
                    {field: "Cette valeur reste liée au paiement comptabilisé."}
                )
    serializer.save()
    consume_approval(order, approval, request.user)
    order.sync_global_status(preserve_manual=True)
    return get_order(order.pk)
