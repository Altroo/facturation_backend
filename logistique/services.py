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


def _get_comptable_emails(company_id):
    return list(
        Membership.objects.filter(company_id=company_id, role__name=ROLE_COMPTABLE)
        .select_related("user")
        .values_list("user__email", flat=True)
    )


@transaction.atomic
def create_orders_from_proformas(*, company_id, proforma_ids, user, defaults):
    """Create one logistics order per detected article brand."""
    if not proforma_ids:
        raise ValidationError({"proformas": _("Sélectionnez au moins une proforma.")})

    proformas = list(
        FactureProForma.objects.filter(
            id__in=proforma_ids,
            company_id=company_id,
        ).select_related("client", "company")
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
            "article",
            "article__marque",
        )
        .order_by("facture_pro_forma_id", "id")
    )
    if not lines:
        raise ValidationError(
            {"proformas": _("Impossible de créer une commande sans lignes proforma.")}
        )

    grouped_lines = defaultdict(list)
    brand_by_key = {}
    for line in lines:
        brand_id, brand = _get_line_brand(line)
        key = brand_id or 0
        grouped_lines[key].append(line)
        brand_by_key[key] = brand

    orders = []
    for key, brand_lines in grouped_lines.items():
        brand = brand_by_key.get(key)
        first_line = brand_lines[0]
        order = LogisticsOrder.objects.create(
            company_id=company_id,
            numero_commande=get_next_numero_logistique(company_id),
            marque=brand,
            devise=defaults.get("devise") or first_line.devise_prix_achat or "MAD",
            fournisseur=defaults.get("fournisseur", ""),
            incoterm=defaults.get("incoterm", ""),
            transport=defaults.get("transport", ""),
            conditions_paiement=defaults.get("conditions_paiement", ""),
            responsable=defaults.get("responsable"),
            date_prevue=defaults.get("date_prevue"),
            date_reelle=defaults.get("date_reelle"),
            statut=defaults.get("statut") or "Réception commande",
            poids_net=defaults.get("poids_net") or Decimal("0"),
            poids_brut=defaults.get("poids_brut") or Decimal("0"),
            volume=defaults.get("volume") or Decimal("0"),
            origine_marchandise=defaults.get("origine_marchandise", ""),
            nature_marchandise=defaults.get("nature_marchandise", ""),
            numero_domiciliation=defaults.get("numero_domiciliation", ""),
            banque=defaults.get("banque", ""),
            montant_titre_importation=defaults.get("montant_titre_importation")
            or Decimal("0"),
            devise_titre_importation=defaults.get("devise_titre_importation") or "MAD",
            date_titre_importation=defaults.get("date_titre_importation"),
            date_validation_titre_importation=defaults.get(
                "date_validation_titre_importation"
            ),
            statut_titre_importation=defaults.get("statut_titre_importation")
            or "À ouvrir",
            methode_paiement=defaults.get("methode_paiement", ""),
            cout_transport=defaults.get("cout_transport") or Decimal("0"),
            frais_transit=defaults.get("frais_transit") or Decimal("0"),
            frais_douane=defaults.get("frais_douane") or Decimal("0"),
            tva=defaults.get("tva") or Decimal("0"),
            livraison_locale=defaults.get("livraison_locale") or Decimal("0"),
            autres_frais=defaults.get("autres_frais") or Decimal("0"),
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
