from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from account.models import Membership
from core.constants import ROLE_COMPTABLE
from facture_proforma.models import FactureProForma, FactureProFormaLine
from notification.models import Notification

from .models import (
    LogisticsOrder,
    LogisticsOrderLine,
    LogisticsOrderProforma,
    LogisticsPaymentInstallment,
)
from .suppliers import ensure_supplier
from .tasks import (
    queue_accounting_payment_email,
    queue_logistics_responsible_payment_email,
)
from .utils import get_next_numero_logistique


def _load_proforma_lines(*, company_id, proforma_ids, for_update=False):
    if not proforma_ids:
        raise ValidationError(
            {"proformas": _("Sélectionnez une facture pro forma acceptée.")}
        )
    proforma_ids = list(dict.fromkeys(proforma_ids))
    proformas = list(
        FactureProForma.objects.filter(
            id__in=proforma_ids,
            company_id=company_id,
        )
        .select_related("client", "company", "source_devis")
        .order_by("id")
    )
    found_ids = {proforma.id for proforma in proformas}
    missing_ids = set(proforma_ids) - found_ids
    if missing_ids:
        raise ValidationError(
            {
                "proformas": _(
                    "La facture pro forma sélectionnée est introuvable ou inaccessible."
                )
            }
        )

    invalid_sources = [
        proforma.numero_facture
        for proforma in proformas
        if proforma.statut != "Accepté"
    ]
    if invalid_sources:
        raise ValidationError(
            {
                "proformas": _(
                    "Seules les commandes client validées (factures pro forma au "
                    "statut Accepté) peuvent lancer un dossier import. Sources "
                    "concernées: %(sources)s."
                )
                % {"sources": ", ".join(invalid_sources[:5])}
            }
        )

    suppliers = {
        (proforma.fournisseur or "").strip().casefold() for proforma in proformas
    }
    if len(suppliers) != 1:
        raise ValidationError(
            {
                "proformas": _(
                    "Toutes les factures pro forma sélectionnées doivent concerner le même fournisseur."
                )
            }
        )

    lines_queryset = FactureProFormaLine.objects.filter(
        facture_pro_forma_id__in=found_ids
    )
    if for_update:
        lines_queryset = lines_queryset.select_for_update(of=("self",))
    lines = list(
        lines_queryset.select_related(
            "facture_pro_forma",
            "facture_pro_forma__client",
            "facture_pro_forma__source_devis",
            "article",
            "article__marque",
        ).order_by("facture_pro_forma_id", "id")
    )
    if not lines:
        raise ValidationError(
            {
                "proformas": _(
                    "Impossible de créer un dossier logistique sans lignes de facture pro forma."
                )
            }
        )

    purchase_currencies = sorted(
        {
            (line.devise_prix_achat or "").strip()
            for line in lines
            if (line.devise_prix_achat or "").strip()
        }
    )
    if len(purchase_currencies) != 1:
        raise ValidationError(
            {
                "proformas": _(
                    "La commande client contient plusieurs devises d'achat. "
                    "Harmonisez les lignes avant de créer le dossier logistique."
                )
            }
        )

    return proformas, lines


def _unique_non_empty(values):
    seen = []
    for value in values:
        if not value:
            continue
        value = str(value)
        if value not in seen:
            seen.append(value)
    return seen


def _proforma_summary(proforma):
    return {
        "id": proforma.id,
        "numero_facture": proforma.numero_facture,
        "source_devis": proforma.source_devis_id,
        "source_devis_numero": (
            proforma.source_devis.numero_devis if proforma.source_devis else ""
        ),
        "client_name": str(proforma.client) if proforma.client else "",
        "fournisseur": proforma.fournisseur,
        "fournisseur_email": proforma.fournisseur_email,
        "project_reference": _project_reference(proforma),
        "date_facture": proforma.date_facture,
        "total_ttc_apres_remise": proforma.total_ttc_apres_remise,
        "devise": proforma.devise,
    }


def _project_reference(proforma):
    return (
        (proforma.numero_bon_commande_client or "").strip()
        or (
            (proforma.source_devis.numero_demande_prix_client or "").strip()
            if proforma.source_devis
            else ""
        )
        or proforma.numero_facture
    )


def build_proforma_source_preview(*, company_id, proforma_ids):
    """Return the accepted customer order and its inherited logistics data."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids
    )
    return {
        "proformas": [_proforma_summary(proforma) for proforma in proformas],
        "fournisseur": proformas[0].fournisseur,
        "fournisseur_email": proformas[0].fournisseur_email,
        "devise": lines[0].devise_prix_achat,
        "articles_count": len(lines),
        "total_quantity": sum((line.quantity for line in lines), Decimal("0")),
        "total_achat": sum(
            (
                (line.prix_achat or Decimal("0")) * (line.quantity or Decimal("0"))
                for line in lines
            ),
            Decimal("0"),
        ),
    }


def _get_comptable_emails(company_id):
    return list(
        Membership.objects.filter(
            company_id=company_id,
            role__name=ROLE_COMPTABLE,
            user__is_active=True,
        )
        .exclude(user__email="")
        .select_related("user")
        .order_by("user__email")
        .values_list("user__email", flat=True)
        .distinct()
    )


@transaction.atomic
def create_orders_from_proformas(*, company_id, proforma_ids, user, defaults):
    """Create one logistics dossier from accepted customer orders."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids, for_update=True
    )
    proforma = proformas[0]
    linked_orders = list(
        LogisticsOrderProforma.objects.filter(proforma__in=proformas).values_list(
            "commande__numero_commande", flat=True
        )
    )
    if linked_orders:
        raise ValidationError(
            {
                "proformas": _(
                    "Une commande client sélectionnée est déjà liée à un dossier logistique (%(orders)s)."
                )
                % {"orders": ", ".join(_unique_non_empty(linked_orders)[:5])}
            }
        )

    linked_source_lines = list(
        LogisticsOrderLine.objects.filter(
            source_line_id__in=[line.id for line in lines]
        )
        .select_related("commande", "source_line")
        .values_list("source_line_id", "commande__numero_commande")
    )
    if linked_source_lines:
        order_numbers = _unique_non_empty(
            order_number for _source_line_id, order_number in linked_source_lines
        )
        raise ValidationError(
            {
                "proformas": _(
                    "Certaines lignes sont déjà liées à un dossier logistique (%(orders)s)."
                )
                % {"orders": ", ".join(order_numbers[:5])}
            }
        )

    order = LogisticsOrder.objects.create(
        fournisseur_record=ensure_supplier(
            company_id, proforma.fournisseur, proforma.fournisseur_email
        ),
        company_id=company_id,
        numero_commande=get_next_numero_logistique(company_id),
        marque=None,
        fournisseur=(proforma.fournisseur or "").strip(),
        fournisseur_email=(proforma.fournisseur_email or "").strip(),
        devise=lines[0].devise_prix_achat,
        conditions_paiement=proforma.termes_paiement or "",
        date_prevue=defaults["date_prevue"],
        date_reelle=defaults.get("date_reelle"),
        origine_marchandise=defaults.get("origine_marchandise") or "",
        nature_marchandise=defaults.get("nature_marchandise") or "",
        responsable_id=defaults.get("responsable") or user.id,
        statut="Réception commande",
        statut_global="À lancer",
        statut_commande_lancement="À lancer",
        created_by_user=user,
    )
    LogisticsOrderProforma.objects.bulk_create(
        [
            LogisticsOrderProforma(commande=order, proforma=selected_proforma)
            for selected_proforma in proformas
        ]
    )

    for line in lines:
        article = line.article
        line_proforma = line.facture_pro_forma
        LogisticsOrderLine.objects.create(
            commande=order,
            proforma=line_proforma,
            source_line=line,
            client=line_proforma.client,
            article=article,
            article_reference=article.reference or "",
            designation=article.designation or "",
            marque_name=str(article.marque) if article.marque else "",
            project_reference=_project_reference(line_proforma),
            quantity=line.quantity,
            prix_achat=line.prix_achat,
            devise_prix_achat=line.devise_prix_achat,
            prix_vente=line.prix_vente,
            devise_prix_vente=line.devise_prix_vente,
        )
    brand_ids = {
        line.article.marque_id for line in lines if line.article.marque_id is not None
    }
    if brand_ids:
        order.marques.set(brand_ids)
        order.marque_id = min(brand_ids)
    order.recalc_costs()
    order.save(update_fields=["marque", "cout_achat", "cout_total", "date_updated"])
    order.add_event(
        user=user,
        action="Création",
        new_value=order.numero_commande,
        note=_("Dossier import généré depuis la commande client validée."),
    )
    return [order]


def send_payment_request_email(order, *, request_user):
    """Persist and queue the accounting handoff after the transaction commits."""
    emails = _get_comptable_emails(order.company_id)
    if not emails:
        raise ValidationError(
            {
                "paiement": _(
                    "Aucune adresse e-mail active du Service Comptable n'est disponible."
                )
            }
        )

    delivery_token = uuid4().hex
    order.demande_paiement_envoyee_le = None
    order.demande_paiement_envoyee_par = request_user
    order.demande_paiement_email_statut = "En attente"
    order.demande_paiement_email_destinataires = emails
    order.demande_paiement_email_erreur = ""
    order.demande_paiement_email_file_token = delivery_token
    order.demande_paiement_email_mis_en_file_le = timezone.now()
    order.demande_paiement_email_task_id = ""
    order.demande_paiement_email_prise_en_charge_le = None
    order.statut_paiement = "En attente"
    if not order.is_supplier_purchase:
        order.statut = "Paiement demandé"
    order.sync_global_status(preserve_manual=False, commit=False)
    order.save(
        update_fields=[
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "demande_paiement_email_statut",
            "demande_paiement_email_destinataires",
            "demande_paiement_email_erreur",
            "demande_paiement_email_file_token",
            "demande_paiement_email_mis_en_file_le",
            "demande_paiement_email_task_id",
            "demande_paiement_email_prise_en_charge_le",
            "statut_paiement",
            "statut",
            "statut_global",
            "date_updated",
        ]
    )
    order.add_event(
        user=request_user,
        action="Demande de paiement",
        new_value="E-mail en attente d'envoi",
    )
    transaction.on_commit(
        lambda order_id=order.id, token=delivery_token: queue_accounting_payment_email(
            order_id, token
        )
    )
    return order


def get_locked_installment(order, installment_id):
    try:
        return order.echeances_paiement.select_for_update().get(pk=installment_id)
    except LogisticsPaymentInstallment.DoesNotExist:
        raise ValidationError(
            {"echeance_id": _("Cette échéance n'appartient pas au dossier.")}
        )


def clear_payment_installment_cache(order):
    getattr(order, "_prefetched_objects_cache", {}).pop("echeances_paiement", None)


def ensure_order_active(order):
    if order.statut_global == "Annulé":
        raise ValidationError(
            {"statut_global": _("Rouvrez le dossier avant de poursuivre le workflow.")}
        )


def invalidate_or_block_active_email_deliveries(order, *, reason):
    installments = list(order.echeances_paiement.select_for_update())
    if order.demande_paiement_email_statut == "Envoi en cours" or any(
        item.preuve_email_statut == "Envoi en cours" for item in installments
    ):
        raise ValidationError(
            {
                "email": _(
                    "Attendez la fin de l'envoi e-mail en cours avant cette action."
                )
            }
        )
    if order.demande_paiement_email_statut == "En attente":
        order.demande_paiement_email_statut = "Échec"
        order.demande_paiement_email_erreur = reason
        order.demande_paiement_email_file_token = ""
        order.demande_paiement_email_mis_en_file_le = None
        order.save(
            update_fields=[
                "demande_paiement_email_statut",
                "demande_paiement_email_erreur",
                "demande_paiement_email_file_token",
                "demande_paiement_email_mis_en_file_le",
                "date_updated",
            ]
        )
    for installment in installments:
        if installment.preuve_email_statut != "En attente":
            continue
        installment.preuve_email_statut = "Échec"
        installment.preuve_email_erreur = reason
        installment.preuve_email_file_token = ""
        installment.preuve_email_mise_en_file_le = None
        installment.save(
            update_fields=[
                "preuve_email_statut",
                "preuve_email_erreur",
                "preuve_email_file_token",
                "preuve_email_mise_en_file_le",
                "date_updated",
            ]
        )


def notify_logistics_responsible(order, message):
    if not order.responsable_id:
        return
    Notification.objects.create(
        user=order.responsable,
        title=_("Paiement logistique validé"),
        message=message,
        notification_type="status_change",
        object_id=order.id,
        target_url=f"/dashboard/logistique/{order.id}?company_id={order.company_id}",
    )
    transaction.on_commit(
        lambda order_id=order.id: queue_logistics_responsible_payment_email(order_id)
    )


def assign_payment_task(order):
    membership = (
        Membership.objects.filter(
            company_id=order.company_id,
            role__name=ROLE_COMPTABLE,
            user__is_active=True,
        )
        .exclude(user__email="")
        .select_related("user")
        .order_by("user_id")
        .first()
    )
    if not membership:
        raise ValidationError(
            {
                "paiement": _(
                    "Aucun utilisateur actif du Service Comptable n'est disponible."
                )
            }
        )
    order.paiement_assigne_a = membership.user
    Notification.objects.create(
        user=membership.user,
        title=_("Effectuer le paiement fournisseur"),
        message=_("Le dossier import %(reference)s est prêt pour paiement.")
        % {"reference": order.numero_commande},
        notification_type="status_change",
        object_id=order.id,
        target_url=f"/dashboard/logistique/{order.id}?company_id={order.company_id}",
    )
    return membership.user
