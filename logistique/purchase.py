"""Business rules shared by the supplier dossier API and its UI."""
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from rest_framework.exceptions import ValidationError

CONDITIONS = {
    "documentary100": ("100 % par remise documentaire", 0, "Remise documentaire", "documentary"),
    "advance30_lc70": ("30 % d’avance et 70 % par lettre de crédit (LC)", 30, "LC", "scheduled"),
    "advance30_documentary70": ("30 % d’avance et 70 % par remise documentaire", 30, "Remise documentaire", "documentary"),
    "advance100": ("100 % d’avance (total inférieur à 18 000)", 100, "Virement", "advance"),
    "advance30_transfer70": ("30 % d’avance et 70 % par virement", 30, "Virement", "scheduled"),
    "receipt100": ("Paiement à la réception", 0, "Virement", "receipt"),
    "shipment100": ("Paiement après l’expédition", 0, "Virement", "shipment"),
}


def validate_condition(code, total):
    if code not in CONDITIONS:
        raise ValidationError({"condition_achat": "Choisissez une condition d’achat."})
    if code == "advance100" and Decimal(total) >= Decimal("18000"):
        raise ValidationError({"condition_achat": "Le paiement intégral d’avance est réservé aux montants inférieurs à 18 000 dans la devise de la proforma fournisseur."})


def create_purchase_schedule(order):
    from .models import LogisticsPaymentInstallment
    validate_condition(order.condition_achat, order.payment_total)
    if order.echeances_paiement.exists():
        return
    _, advance, method, trigger = CONDITIONS[order.condition_achat]
    amounts = []
    if advance:
        amounts.append((advance, "Virement", "advance"))
    if advance < 100:
        amounts.append((100 - advance, method, trigger))
    assigned = Decimal("0")
    for index, (percentage, payment_method, event) in enumerate(amounts):
        amount = (order.payment_total - assigned if index == len(amounts) - 1 else
                  (order.payment_total * Decimal(percentage) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        assigned += amount
        if amount == 0:
            continue
        LogisticsPaymentInstallment.objects.create(commande=order, pourcentage=percentage,
            montant_prevu=amount, devise=order.devise_proforma_fournisseur,
            methode_paiement=payment_method, declencheur=event)


def receipt_complete(order):
    return bool(order.date_reelle and order.lignes.exists() and not any(
        line.received_quantity < line.quantity for line in order.lignes.all()
        if (line.article.type_article or "").lower() == "produit" and order.company.stock_management_enabled))


def payment_blocker(order, installment):
    if not order.is_proforma_step_complete:
        return "Validez d’abord la proforma fournisseur."
    if order.statut_global == "Annulé":
        return "Rouvrez le dossier pour poursuivre."
    if installment.declencheur == "documentary" and not (order.date_arrivee_maroc and order.documents_remis_banque_le):
        return "En attente de l’arrivée au Maroc et de la remise des documents à la banque."
    if installment.declencheur == "shipment" and not order.date_expedition_reelle:
        return "En attente de l’expédition réelle."
    if installment.declencheur == "receipt" and not receipt_complete(order):
        return "En attente de la réception complète."
    return ""


def preparation_blocker(order):
    if not order.is_proforma_step_complete:
        return "Validez d’abord la proforma fournisseur."
    for item in order.echeances_paiement.all():
        if item.declencheur == "advance" and not item.paiement_valide_le:
            return "Faites valider l’avance et son justificatif par le comptable."
        if item.declencheur == "advance" and not item.preuve_envoyee_fournisseur_le:
            return "Indiquez l’envoi du justificatif de l’avance au fournisseur."
    return ""


def validate_purchase_transition(order, status, *, enforce_sequence=True):
    if not order.is_supplier_purchase:
        return
    stages = ["Proforma", "Production", "Expédition", "Transit", "Dédouanement", "Réception locale", "Livraison client", "Clôture"]
    if status not in stages:
        raise ValidationError({"statut": "Cette phase n’appartient pas au parcours d’achat fournisseur."})
    if enforce_sequence and status in stages and order.statut in stages and stages.index(status) < stages.index(order.statut):
        raise ValidationError({"statut": "Cette action ferait revenir le dossier à une phase antérieure."})
    if status in {"Production", "Expédition", "Transit", "Dédouanement", "Réception locale", "Livraison client", "Clôture"}:
        reason = preparation_blocker(order)
        if reason:
            raise ValidationError({"statut": reason})
        if not order.production_confirmee_le or not order.date_expedition_prevue:
            raise ValidationError({"statut": "Renseignez la confirmation de production et la date d’expédition prévue."})
    if status in {"Expédition", "Transit", "Dédouanement", "Réception locale", "Livraison client", "Clôture"} and not order.date_expedition_reelle:
        raise ValidationError({"statut": "Renseignez la date réelle d’expédition."})
    if status in {"Réception locale", "Livraison client", "Clôture"} and not receipt_complete(order):
        raise ValidationError({"statut": "Enregistrez la réception complète des articles."})
    if status == "Clôture" and order.solde_restant:
        raise ValidationError({"statut": "Réglez le solde restant avant la clôture."})


def workflow_summary(order):
    if not order.is_supplier_purchase:
        return {}
    items = list(order.echeances_paiement.all())
    reason = preparation_blocker(order)
    payments = [{"id": item.id, "declencheur": item.declencheur,
        "demande_possible": not item.demandee_le and not item.paiement_valide_le and not payment_blocker(order, item),
        "raison_attente": payment_blocker(order, item)} for item in items]
    if not order.is_proforma_step_complete:
        action = "Renseigner et valider la proforma fournisseur"
    elif reason:
        action = reason
    elif not order.production_confirmee_le:
        action = "Confirmer le début de production et renseigner la date d’expédition prévue"
    elif not order.date_expedition_reelle:
        action = "Suivre la production puis enregistrer l’expédition"
    elif not receipt_complete(order):
        action = "Suivre le transit puis enregistrer les quantités reçues"
    elif order.solde_restant:
        action = "Régler le solde restant"
    else:
        action = "Clôturer le dossier" if order.statut != "Clôture" else "Dossier clôturé"
    if order.statut_global == "Annulé":
        action = "Dossier annulé"
    return {"prochaine_action": action, "preparation_possible": not reason,
        "raison_preparation": reason, "paiements": payments,
        "conditions": [{"value": key, "label": value[0]} for key, value in CONDITIONS.items()]}
