from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from account.models import Membership
from core.constants import ROLE_COMPTABLE
from facture_proforma.models import FactureProForma, FactureProFormaLine

from .models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma
from .utils import get_next_numero_logistique


def _load_proforma_lines(*, company_id, proforma_ids, for_update=False):
    if not proforma_ids:
        raise ValidationError({"proformas": _("Sélectionnez au moins une proforma.")})
    proforma_ids = list(dict.fromkeys(proforma_ids))
    if len(proforma_ids) != 1:
        raise ValidationError(
            {
                "proformas": _(
                    "Sélectionnez une seule commande client validée par dossier logistique."
                )
            }
        )

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
            {"proformas": _("Certaines proformas sont introuvables ou inaccessibles.")}
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
                    "Seules les commandes client validées (proformas au statut Accepté) peuvent lancer un dossier import. Sources concernées: %(sources)s."
                )
                % {"sources": ", ".join(invalid_sources[:5])}
            }
        )

    missing_suppliers = [
        proforma.numero_facture
        for proforma in proformas
        if not (proforma.fournisseur or "").strip()
    ]
    if missing_suppliers:
        raise ValidationError(
            {
                "proformas": _(
                    "Renseignez le fournisseur sur la commande client avant de créer le dossier logistique. Sources concernées: %(sources)s."
                )
                % {"sources": ", ".join(missing_suppliers[:5])}
            }
        )

    lines_queryset = FactureProFormaLine.objects.filter(
        facture_pro_forma_id__in=found_ids
    )
    if for_update:
        lines_queryset = lines_queryset.select_for_update(of=("self",))
    lines = list(
        lines_queryset
        .select_related(
            "facture_pro_forma",
            "facture_pro_forma__client",
            "facture_pro_forma__source_devis",
            "article",
            "article__marque",
        )
        .order_by("facture_pro_forma_id", "id")
    )
    if not lines:
        raise ValidationError(
            {"proformas": _("Impossible de créer une commande sans lignes proforma.")}
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
                    "La commande client contient plusieurs devises d'achat. Harmonisez les lignes avant de créer le dossier logistique."
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
        "project_reference": proforma.numero_bon_commande_client or "",
        "date_facture": proforma.date_facture,
        "total_ttc_apres_remise": proforma.total_ttc_apres_remise,
        "devise": proforma.devise,
    }


def build_proforma_source_preview(*, company_id, proforma_ids):
    """Return the accepted customer order and its inherited logistics data."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids
    )
    summary = _proforma_summary(proformas[0])
    summary.update(
        {
            "devise": lines[0].devise_prix_achat,
            "articles_count": len(lines),
            "total_quantity": sum(
                (line.quantity for line in lines), Decimal("0")
            ),
            "total_achat": sum(
                (
                    (line.prix_achat or Decimal("0"))
                    * (line.quantity or Decimal("0"))
                    for line in lines
                ),
                Decimal("0"),
            ),
        }
    )
    return {"proformas": [summary]}


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
    """Create one logistics dossier from one accepted customer order."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids, for_update=True
    )
    proforma = proformas[0]
    linked_orders = list(
        LogisticsOrderProforma.objects.filter(proforma=proforma).values_list(
            "commande__numero_commande", flat=True
        )
    )
    if linked_orders:
        raise ValidationError(
            {
                "proformas": _(
                    "Cette commande client est déjà liée à un dossier logistique (%(orders)s)."
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
            order_number for _, order_number in linked_source_lines
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
        company_id=company_id,
        numero_commande=get_next_numero_logistique(company_id),
        marque=None,
        fournisseur=proforma.fournisseur.strip(),
        fournisseur_email=(proforma.fournisseur_email or "").strip(),
        devise=lines[0].devise_prix_achat,
        conditions_paiement=proforma.termes_paiement or "",
        date_prevue=defaults["date_prevue"],
        date_reelle=defaults.get("date_reelle"),
        origine_marchandise=defaults.get("origine_marchandise") or "",
        nature_marchandise=defaults.get("nature_marchandise") or "",
        responsable_id=defaults.get("responsable"),
        statut="Réception commande",
        statut_global="À lancer",
        statut_commande_lancement="À lancer",
        created_by_user=user,
    )
    LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)

    for line in lines:
        article = line.article
        LogisticsOrderLine.objects.create(
            commande=order,
            proforma=proforma,
            source_line=line,
            client=proforma.client,
            article=article,
            article_reference=article.reference or "",
            designation=article.designation or "",
            marque_name=str(article.marque) if article.marque else "",
            project_reference=proforma.numero_bon_commande_client or "",
            quantity=line.quantity,
            prix_achat=line.prix_achat,
            devise_prix_achat=line.devise_prix_achat,
            prix_vente=line.prix_vente,
            devise_prix_vente=line.devise_prix_vente,
        )
    order.recalc_costs()
    order.save(update_fields=["cout_achat", "cout_total", "date_updated"])
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
    from .tasks import queue_accounting_payment_email

    transaction.on_commit(
        lambda order_id=order.id, token=delivery_token: queue_accounting_payment_email(
            order_id, token
        )
    )
    return order
