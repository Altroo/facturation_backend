"""Business rules shared by the supplier dossier API and its UI."""

from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError

from .historical import historical_steps
from .models import LogisticsPaymentInstallment

CONDITIONS = {
    "documentary100": (
        "100 % par remise documentaire",
        0,
        "Remise documentaire",
        "documentary",
    ),
    "advance30_lc70": (
        "30 % d’avance et 70 % par lettre de crédit (LC)",
        30,
        "LC",
        "scheduled",
    ),
    "advance30_documentary70": (
        "30 % d’avance et 70 % par remise documentaire",
        30,
        "Remise documentaire",
        "documentary",
    ),
    "advance100": (
        "100 % d’avance (total inférieur à 18 000)",
        100,
        "Virement",
        "advance",
    ),
    "advance30_transfer70": (
        "30 % d’avance et 70 % par virement",
        30,
        "Virement",
        "scheduled",
    ),
    "receipt100": ("Paiement à la réception", 0, "Virement", "receipt"),
    "shipment100": ("Paiement après l’expédition", 0, "Virement", "shipment"),
}


def validate_condition(code, total):
    if code not in CONDITIONS:
        raise ValidationError({"condition_achat": "Choisissez une condition d’achat."})
    if code == "advance100" and Decimal(total) >= Decimal("18000"):
        raise ValidationError(
            {
                "condition_achat": "Le paiement intégral d’avance est réservé aux montants inférieurs à 18 000 dans la devise de la proforma fournisseur."
            }
        )


def create_purchase_schedule(order):
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
        amount = (
            order.payment_total - assigned
            if index == len(amounts) - 1
            else (order.payment_total * Decimal(percentage) / 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        assigned += amount
        if amount == 0:
            continue
        LogisticsPaymentInstallment.objects.create(
            commande=order,
            pourcentage=percentage,
            montant_prevu=amount,
            devise=order.devise_proforma_fournisseur,
            methode_paiement=payment_method,
            declencheur=event,
        )


def receipt_complete(order):
    return bool(
        order.date_reelle
        and order.lignes.exists()
        and not any(
            line.received_quantity < line.quantity
            for line in order.lignes.all()
            if (line.article.type_article or "").lower() == "produit"
            and order.company.stock_management_enabled
        )
    )


def payment_blocker(order, installment):
    if not order.is_proforma_step_complete:
        return "Validez d’abord la proforma fournisseur."
    if order.statut_global == "Annulé":
        return "Rouvrez le dossier pour poursuivre."
    if installment.declencheur == "documentary" and not (
        order.date_arrivee_maroc and order.documents_remis_banque_le
    ):
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
        if item.demandee_le and not item.paiement_valide_le:
            return "Attendez la validation du paiement et de son justificatif par le comptable."
        if item.declencheur == "advance" and not item.paiement_valide_le:
            return "Faites valider l’avance et son justificatif par le comptable."
        if item.declencheur == "advance" and not item.preuve_envoyee_fournisseur_le:
            return "Indiquez l’envoi du justificatif de l’avance au fournisseur."
    return ""


def purchase_steps(order):
    """Ordered business stages. Deferred payments stay after their triggering event."""
    items = list(order.echeances_paiement.all())
    advance = [item for item in items if item.declencheur == "advance"]
    balance = [item for item in items if item.declencheur != "advance"]
    received = receipt_complete(order)
    shipped = bool(order.date_expedition_reelle or received)
    title_done = bool(
        order.numero_domiciliation.strip()
        and order.banque.strip()
        and order.date_titre_importation
        and order.titre_importation_file
        and order.montant_titre_importation == order.payment_total
        and order.devise_titre_importation == order.devise_proforma_fournisseur
    )
    steps = [
        {"key": "dossier", "label": "Dossier", "completed": True},
        {
            "key": "proforma",
            "label": "Proforma et conformité",
            "completed": order.is_proforma_step_complete,
        },
        {"key": "titre", "label": "Titre d’importation", "completed": title_done},
    ]

    def payments(key, label, selected):
        return {
            "key": key,
            "label": label,
            "completed": bool(selected)
            and all(
                item.paiement_valide_le
                and (
                    item.declencheur != "advance" or item.preuve_envoyee_fournisseur_le
                )
                for item in selected
            ),
            "payment_ids": [item.pk for item in selected],
        }

    if advance:
        steps.append(payments("paiement", "Avance et comptabilité", advance))
    steps.extend(
        [
            {
                "key": "production",
                "label": "Préparation fournisseur",
                "completed": bool(
                    order.production_confirmee_le and order.date_expedition_prevue
                )
                or shipped,
            },
            {"key": "expedition", "label": "Expédition", "completed": shipped},
        ]
    )
    if balance and order.condition_achat not in {
        "documentary100",
        "advance30_documentary70",
        "receipt100",
    }:
        steps.append(payments("solde", "Paiement et comptabilité", balance))
    steps.append(
        {
            "key": "transit",
            "label": "Transit et douane",
            "completed": bool(
                received
                or (
                    order.date_arrivee_maroc
                    and (
                        order.condition_achat
                        not in {"documentary100", "advance30_documentary70"}
                        or order.documents_remis_banque_le
                    )
                )
            ),
        }
    )
    if balance and order.condition_achat in {
        "documentary100",
        "advance30_documentary70",
    }:
        steps.append(payments("solde", "Paiement et comptabilité", balance))
    steps.append(
        {
            "key": "reception",
            "label": "Réception et livraison",
            "completed": received and order.statut in {"Livraison client", "Clôture"},
        }
    )
    if balance and order.condition_achat == "receipt100":
        steps.append(payments("solde", "Paiement et comptabilité", balance))
    steps.append(
        {
            "key": "couts",
            "label": "Clôture et coût réel",
            "completed": order.statut == "Clôture",
        }
    )
    current = next((step["key"] for step in steps if not step["completed"]), "couts")
    # A submitted accounting task takes precedence, including future-dated balances.
    pending = next(
        (item for item in items if item.demandee_le and not item.paiement_valide_le),
        None,
    )
    if pending and order.is_proforma_step_complete:
        current = "paiement" if pending.declencheur == "advance" else "solde"
    current_index = next(
        index for index, step in enumerate(steps) if step["key"] == current
    )
    for index, step in enumerate(steps):
        step["accessible"] = index <= current_index
    return steps, current


def validate_purchase_transition(order, status, *, enforce_sequence=True):
    if not order.is_supplier_purchase:
        return
    stages = [
        "Proforma",
        "Production",
        "Expédition",
        "Transit",
        "Dédouanement",
        "Réception locale",
        "Livraison client",
        "Clôture",
    ]
    if status not in stages:
        raise ValidationError(
            {"statut": "Cette phase n’appartient pas au parcours d’achat fournisseur."}
        )
    if (
        enforce_sequence
        and status in stages
        and order.statut in stages
        and stages.index(status) < stages.index(order.statut)
    ):
        raise ValidationError(
            {"statut": "Cette action ferait revenir le dossier à une phase antérieure."}
        )
    if status in {
        "Production",
        "Expédition",
        "Transit",
        "Dédouanement",
        "Réception locale",
        "Livraison client",
        "Clôture",
    }:
        reason = preparation_blocker(order)
        if reason:
            raise ValidationError({"statut": reason})
        if not order.production_confirmee_le or not order.date_expedition_prevue:
            raise ValidationError(
                {
                    "statut": "Renseignez la confirmation de production et la date d’expédition prévue."
                }
            )
    if (
        status
        in {
            "Expédition",
            "Transit",
            "Dédouanement",
            "Réception locale",
            "Livraison client",
            "Clôture",
        }
        and not order.date_expedition_reelle
    ):
        raise ValidationError({"statut": "Renseignez la date réelle d’expédition."})
    if status in {
        "Réception locale",
        "Livraison client",
        "Clôture",
    } and not receipt_complete(order):
        raise ValidationError(
            {"statut": "Enregistrez la réception complète des articles."}
        )
    if status == "Clôture" and order.devise != "MAD" and order.cout_achat_mad is None:
        raise ValidationError(
            {
                "cout_achat_mad": "Renseignez le coût d’achat converti en MAD par la comptabilité avant la clôture."
            }
        )
    if status == "Clôture" and order.solde_restant:
        raise ValidationError({"statut": "Réglez le solde restant avant la clôture."})


def workflow_summary(order):
    if not order.is_supplier_purchase:
        steps, current = historical_steps(order)
        return {"etapes": steps, "etape_courante": current}
    items = list(order.echeances_paiement.all())
    reason = preparation_blocker(order)
    payments = [
        {
            "id": item.id,
            "declencheur": item.declencheur,
            "demande_possible": not item.demandee_le
            and not item.paiement_valide_le
            and not payment_blocker(order, item),
            "raison_attente": payment_blocker(order, item),
        }
        for item in items
    ]
    if not order.is_proforma_step_complete:
        action = "Renseigner et valider la proforma fournisseur"
    elif reason:
        action = reason
    elif not order.production_confirmee_le:
        action = (
            "Confirmer le début de production et renseigner la date d’expédition prévue"
        )
    elif not order.date_expedition_reelle:
        action = "Suivre la production puis enregistrer l’expédition"
    elif not receipt_complete(order):
        action = "Suivre le transit puis enregistrer les quantités reçues"
    elif order.solde_restant:
        action = "Régler le solde restant"
    else:
        action = (
            "Clôturer le dossier" if order.statut != "Clôture" else "Dossier clôturé"
        )
    if order.statut_global == "Annulé":
        action = "Dossier annulé"
    steps, current = purchase_steps(order)
    if order.statut_global != "Annulé" and order.statut != "Clôture":
        action = {
            "proforma": "Renseigner et valider la proforma fournisseur",
            "titre": "Renseigner et vérifier le titre d’importation",
            "paiement": reason or "Transmettre l’avance au comptable",
            "production": "Confirmer le début de production et renseigner la date d’expédition prévue",
            "expedition": "Enregistrer l’expédition réelle",
            "transit": "Renseigner l’arrivée au Maroc et les documents de transit",
            "reception": "Enregistrer les quantités reçues puis confirmer la livraison",
            "solde": "Terminer le paiement et sa validation comptable",
            "couts": "Vérifier les coûts et clôturer le dossier",
        }.get(current, action)
    return {
        "etapes": steps,
        "etape_courante": current,
        "prochaine_action": action,
        "preparation_possible": not reason,
        "raison_preparation": reason,
        "paiements": payments,
        "conditions": [
            {"value": key, "label": value[0]} for key, value in CONDITIONS.items()
        ],
    }


PROGRESS_FIELDS = {
    "production": {"date_expedition_prevue", "confirmer_production"},
    "expedition": {
        "date_expedition_reelle",
        "transport",
        "documents_originaux_requis",
        "statut_documents_originaux",
        "documents_originaux_file",
    },
    "transit": {
        "autres_frais_virement_actif",
        "autres_frais_virement",
        "description_frais_virement",
        "autres_frais_cash_actif",
        "autres_frais_cash",
        "description_frais_cash",
        "date_arrivee_maroc",
        "documents_remis_banque_le",
        "cout_transport",
        "frais_transit",
        "frais_douane",
        "tva",
    },
    "reception": {"date_reelle", "bon_reception_file"},
    "couts": {
        "cout_achat_mad",
        "autres_frais_virement_actif",
        "autres_frais_virement",
        "description_frais_virement",
        "autres_frais_cash_actif",
        "autres_frais_cash",
        "description_frais_cash",
        "cout_transport",
        "frais_transit",
        "frais_douane",
        "tva",
        "livraison_locale",
        "autres_frais",
    },
}


def action_step(order, data):
    action = data.get("action")
    if action == "corriger_paiement":
        step = data.get("etape")
        if step not in {"paiement", "solde"}:
            raise ValidationError(
                {"etape": "Choisissez l’étape du paiement à corriger."}
            )
        return step
    if action == "corriger_reception":
        return "reception"
    if action in {"dossier", "proforma", "titre", "reception"}:
        return action
    if action != "progression":
        return None
    step = data.get("etape")
    supplied = set(data) - {
        "action",
        "etape",
        "correction_id",
        "remarque",
        "statut",
        "justificatifs_file",
    }
    if not step:
        step = next(
            (
                key
                for key, fields in PROGRESS_FIELDS.items()
                if supplied and supplied <= fields
            ),
            None,
        )
        if not step and not supplied:
            step = {
                "Production": "production",
                "Expédition": "expedition",
                "Transit": "transit",
                "Dédouanement": "transit",
                "Réception locale": "reception",
                "Livraison client": "reception",
                "Clôture": "couts",
            }.get(data.get("statut"))
            if not step and not data.get("statut"):
                return None
    if step not in PROGRESS_FIELDS or supplied - PROGRESS_FIELDS[step]:
        raise ValidationError(
            {"etape": "Modifiez uniquement les champs de l’étape sélectionnée."}
        )
    targets = {
        "production": {"Production"},
        "expedition": {"Expédition"},
        "transit": {"Transit", "Dédouanement"},
        "reception": {"Réception locale", "Livraison client"},
        "couts": {"Clôture"},
    }
    if data.get("statut") and data["statut"] not in targets[step] | {order.statut}:
        raise ValidationError(
            {"statut": "Cette phase ne correspond pas à l’étape sélectionnée."}
        )
    return step
