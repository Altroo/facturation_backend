from collections import defaultdict
from decimal import Decimal

from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from account.models import Membership
from core.constants import ROLE_COMPTABLE
from facture_proforma.models import FactureProForma, FactureProFormaLine

from .models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma
from .utils import get_next_numero_logistique


def _get_line_brand(line):
    article = line.article
    return article.marque_id, article.marque


def _line_purchase_currency(line):
    return line.devise_prix_achat or "MAD"


def _brand_name(brand):
    return str(brand) if brand else _("Sans marque")


def _load_proforma_lines(*, company_id, proforma_ids):
    if not proforma_ids:
        raise ValidationError({"proformas": _("Sélectionnez au moins une proforma.")})

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

    lines = list(
        FactureProFormaLine.objects.filter(facture_pro_forma_id__in=found_ids)
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

    missing_brand_refs = [
        line.article.reference or line.article.designation or str(line.article_id)
        for line in lines
        if not line.article.marque_id
    ]
    if missing_brand_refs:
        raise ValidationError(
            {
                "proformas": _(
                    "Tous les articles sélectionnés doivent avoir une marque avant la création logistique. Articles concernés: %(articles)s."
                )
                % {"articles": ", ".join(missing_brand_refs[:5])}
            }
        )

    return proformas, lines


def _group_lines_by_brand(lines):
    grouped_lines = defaultdict(list)
    brand_by_key = {}
    for line in lines:
        brand_id, brand = _get_line_brand(line)
        grouped_lines[brand_id].append(line)
        brand_by_key[brand_id] = brand
    return grouped_lines, brand_by_key


def _validate_brand_currencies(grouped_lines, brand_by_key):
    for key, brand_lines in grouped_lines.items():
        currencies = sorted({_line_purchase_currency(line) for line in brand_lines})
        if len(currencies) > 1:
            raise ValidationError(
                {
                    "proformas": _(
                        "La marque %(marque)s contient plusieurs devises d'achat (%(devises)s). Séparez la sélection par devise avant de créer la commande logistique."
                    )
                    % {
                        "marque": _brand_name(brand_by_key.get(key)),
                        "devises": ", ".join(currencies),
                    }
                }
            )


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
        "project_reference": proforma.numero_bon_commande_client or "",
        "date_facture": proforma.date_facture,
        "total_ttc_apres_remise": proforma.total_ttc_apres_remise,
        "devise": proforma.devise,
    }


def build_proforma_source_preview(*, company_id, proforma_ids):
    """Return selected proformas grouped by brand for the logistics add form."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids
    )
    grouped_lines, brand_by_key = _group_lines_by_brand(lines)
    _validate_brand_currencies(grouped_lines, brand_by_key)

    brands = []
    for key, brand_lines in grouped_lines.items():
        brand = brand_by_key.get(key)
        proforma_by_id = {
            line.facture_pro_forma_id: line.facture_pro_forma for line in brand_lines
        }
        source_devis_numbers = _unique_non_empty(
            proforma.source_devis.numero_devis if proforma.source_devis else ""
            for proforma in proforma_by_id.values()
        )
        brands.append(
            {
                "marque": key,
                "marque_name": _brand_name(brand),
                "devise": _line_purchase_currency(brand_lines[0]),
                "proforma_ids": list(proforma_by_id.keys()),
                "proforma_numbers": _unique_non_empty(
                    proforma.numero_facture for proforma in proforma_by_id.values()
                ),
                "source_devis_numbers": source_devis_numbers,
                "client_names": _unique_non_empty(
                    line.facture_pro_forma.client for line in brand_lines
                ),
                "project_references": _unique_non_empty(
                    line.facture_pro_forma.numero_bon_commande_client
                    for line in brand_lines
                ),
                "articles_count": len(brand_lines),
                "total_quantity": sum(
                    (line.quantity for line in brand_lines), Decimal("0")
                ),
                "total_achat": sum(
                    (
                        (line.prix_achat or Decimal("0"))
                        * (line.quantity or Decimal("0"))
                        for line in brand_lines
                    ),
                    Decimal("0"),
                ),
            }
        )

    brands.sort(key=lambda item: item["marque_name"])
    return {
        "proformas": [_proforma_summary(proforma) for proforma in proformas],
        "brands": brands,
    }


def _detail_value(detail, defaults, field):
    if detail and detail.get(field) not in (None, ""):
        return detail.get(field)
    return defaults.get(field)


def _get_brand_creation_defaults(*, brand_key, brand, grouped_count, defaults):
    details = {
        item.get("marque"): item for item in defaults.get("brand_details", []) or []
    }
    detail = details.get(brand_key)
    if not detail and grouped_count > 1:
        raise ValidationError(
            {
                "brand_details": _(
                    "Renseignez les informations logistiques pour la marque %(marque)s."
                )
                % {"marque": _brand_name(brand)}
            }
        )

    required_fields = ("date_prevue", "origine_marchandise", "nature_marchandise")
    missing_fields = [
        field
        for field in required_fields
        if _detail_value(detail, defaults, field) in (None, "")
    ]
    if missing_fields:
        raise ValidationError(
            {
                "brand_details": _(
                    "Champs obligatoires manquants pour la marque %(marque)s: %(fields)s."
                )
                % {
                    "marque": _brand_name(brand),
                    "fields": ", ".join(missing_fields),
                }
            }
        )

    return {
        "date_prevue": _detail_value(detail, defaults, "date_prevue"),
        "date_reelle": _detail_value(detail, defaults, "date_reelle"),
        "origine_marchandise": _detail_value(
            detail, defaults, "origine_marchandise"
        ),
        "nature_marchandise": _detail_value(detail, defaults, "nature_marchandise"),
    }


def _get_comptable_emails(company_id):
    return list(
        Membership.objects.filter(company_id=company_id, role__name=ROLE_COMPTABLE)
        .select_related("user")
        .values_list("user__email", flat=True)
    )


@transaction.atomic
def create_orders_from_proformas(*, company_id, proforma_ids, user, defaults):
    """Create one logistics order per detected article brand."""
    proformas, lines = _load_proforma_lines(
        company_id=company_id, proforma_ids=proforma_ids
    )
    grouped_lines, brand_by_key = _group_lines_by_brand(lines)
    _validate_brand_currencies(grouped_lines, brand_by_key)

    orders = []
    for key, brand_lines in grouped_lines.items():
        brand = brand_by_key.get(key)
        first_line = brand_lines[0]
        brand_defaults = _get_brand_creation_defaults(
            brand_key=key,
            brand=brand,
            grouped_count=len(grouped_lines),
            defaults=defaults,
        )
        order = LogisticsOrder.objects.create(
            company_id=company_id,
            numero_commande=get_next_numero_logistique(company_id),
            marque=brand,
            devise=_line_purchase_currency(first_line),
            date_prevue=brand_defaults["date_prevue"],
            date_reelle=brand_defaults["date_reelle"],
            origine_marchandise=brand_defaults["origine_marchandise"],
            nature_marchandise=brand_defaults["nature_marchandise"],
            created_by_user=user,
        )
        linked_proformas = {
            line.facture_pro_forma_id: line.facture_pro_forma for line in brand_lines
        }
        for proforma in linked_proformas.values():
            LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)

        for line in brand_lines:
            article = line.article
            LogisticsOrderLine.objects.create(
                commande=order,
                proforma=line.facture_pro_forma,
                source_line=line,
                client=line.facture_pro_forma.client,
                article=article,
                article_reference=article.reference or "",
                designation=article.designation or "",
                marque_name=str(article.marque) if article.marque else "",
                project_reference=line.facture_pro_forma.numero_bon_commande_client
                or "",
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
            note=_("Commande générée depuis les proformas sélectionnées."),
        )
        orders.append(order)

    return orders


def send_payment_request_email(order, *, request_user):
    """Email accounting users and record payment request traceability."""
    emails = _get_comptable_emails(order.company_id)
    if emails:
        attachments = []
        for field_name in ("proforma_fournisseur_file", "titre_importation_file"):
            file_obj = getattr(order, field_name)
            if file_obj:
                attachments.append(file_obj)

        message = EmailMessage(
            subject=_("Demande de paiement logistique %(numero)s")
            % {"numero": order.numero_commande},
            body=_(
                "Une demande de paiement est en attente de traitement pour la "
                "commande logistique %(numero)s."
            )
            % {"numero": order.numero_commande},
            to=emails,
        )
        for file_obj in attachments:
            message.attach_file(file_obj.path)
        message.send(fail_silently=True)

    order.demande_paiement_envoyee_le = timezone.now()
    order.demande_paiement_envoyee_par = request_user
    order.statut_paiement = "En attente"
    order.statut = "Paiement demandé"
    order.save(
        update_fields=[
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "statut_paiement",
            "statut",
            "date_updated",
        ]
    )
    order.add_event(
        user=request_user,
        action="Demande de paiement",
        new_value="En attente",
    )
    return order
