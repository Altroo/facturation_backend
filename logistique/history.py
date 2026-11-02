"""Resolve value start times from recorded dossier events and status snapshots."""
import re
from datetime import date, datetime
from pathlib import Path

from django.utils import timezone

from .purchase import CONDITIONS

# Different actions can update the same status. Keep their timeline together.
STATUS_FIELDS = {
    "Changement statut Commande & lancement": "statut_commande_lancement",
    "Demande de pro forma fournisseur": "statut_commande_lancement",
    "Changement de statut": "statut",
    "Modification : Phase du dossier": "statut",
    "Changement de statut global": "statut_global",
    "Contrôle pro forma fournisseur": "statut_proforma_conformite",
    "Correction de la pro forma fournisseur demandée": "statut_proforma_conformite",
    "Validation de la pro forma fournisseur": "statut_proforma_conformite",
    "Refus de la pro forma fournisseur": "statut_proforma_conformite",
    "Modification : Décision sur la proforma fournisseur": "statut_proforma_conformite",
    "Modification : État des documents originaux": "statut_documents_originaux",
}


def _values(event):
    if event.action.startswith("Modification : "):
        full = re.fullmatch(
            r"Ancienne valeur :\n([\s\S]*?)\n\nNouvelle valeur :\n([\s\S]*)", event.note
        )
        if full:
            return full.group(1), full.group(2)
    return event.old_value, event.new_value


def _recorded_status_start(event, field, snapshots):
    previous = [row for row in snapshots if row["history_date"] <= event.date_created]
    index = len(previous) - 1
    # The new status is saved just before the event is recorded.
    if event.old_value != event.new_value:
        while index >= 0 and previous[index][field] == event.new_value:
            index -= 1
    if index < 0 or previous[index][field] != event.old_value:
        return None
    while index > 0 and previous[index - 1][field] == event.old_value:
        index -= 1
    # An oldest retained update alone does not prove when its value began.
    if index == 0 and previous[index]["history_type"] != "+":
        return None
    return previous[index]["history_date"]


def event_value_dates(order):
    events = sorted(
        order.events.all(), key=lambda event: (event.date_created, event.pk)
    )
    status_fields = sorted(set(STATUS_FIELDS.values()))
    snapshots = (
        list(
            order.history.order_by("history_date", "history_id").values(
                "history_date",
                "history_type",
                *status_fields,
            )
        )
        if any(event.action in STATUS_FIELDS for event in events)
        else []
    )
    state, dates = {}, {}
    for event in events:
        field = STATUS_FIELDS.get(event.action)
        key = field or event.action
        old_value, new_value = _values(event)
        prior = state.get(key)
        since = prior[1] if prior and prior[0] == old_value else None
        if field:
            recorded = _recorded_status_start(event, field, snapshots)
            if recorded is not None and (since is None or recorded > since):
                since = recorded
        dates[event.pk] = {
            "before": since,
            "after": event.date_created if old_value != new_value else since,
        }
        # Saving the same value must not restart its recorded lifetime.
        state[key] = (
            new_value,
            event.date_created if old_value != new_value else since,
        )
    return dates


BUSINESS_FIELDS = {
    "fournisseur": "Fournisseur",
    "fournisseur_email": "E-mail du fournisseur",
    "marque": "Contact fournisseur",
    "responsable": "Responsable du dossier",
    "date_prevue": "Date prévue du dossier",
    "date_commande_client": "Date de commande client",
    "numero_proforma_fournisseur": "Numéro de proforma fournisseur",
    "date_proforma_fournisseur": "Date de proforma fournisseur",
    "montant_proforma_fournisseur": "Montant de proforma fournisseur",
    "devise_proforma_fournisseur": "Devise de proforma fournisseur",
    "condition_achat": "Conditions d’achat",
    "incoterm": "Incoterm",
    "delai_proforma_jours": "Délai fournisseur (jours)",
    "origine_marchandise": "Origine de la marchandise",
    "nature_marchandise": "Nature de la marchandise",
    "poids_net": "Poids net (kg)",
    "poids_brut": "Poids brut (kg)",
    "volume": "Volume (m³)",
    "ecart_prix_proforma": "Anomalie de prix",
    "ecart_quantite_proforma": "Anomalie de quantité",
    "ecart_autre_proforma": "Autre anomalie",
    "notes_ecarts_proforma": "Détail des anomalies / motif",
    "statut_proforma_conformite": "Décision sur la proforma fournisseur",
    "proforma_fournisseur_file": "Proforma fournisseur jointe",
    "numero_domiciliation": "Numéro de domiciliation",
    "banque": "Banque",
    "montant_titre_importation": "Montant du titre d’importation",
    "devise_titre_importation": "Devise du titre d’importation",
    "date_titre_importation": "Date du titre d’importation",
    "titre_importation_file": "Titre d’importation joint",
    "date_expedition_prevue": "Date d’expédition prévue",
    "production_confirmee_le": "Début de production confirmé",
    "date_expedition_reelle": "Date réelle d’expédition",
    "date_arrivee_maroc": "Date d’arrivée au Maroc",
    "documents_remis_banque_le": "Documents remis à la banque le",
    "date_reelle": "Date réelle de réception",
    "transport": "Transport",
    "documents_originaux_requis": "Documents originaux requis",
    "statut_documents_originaux": "État des documents originaux",
    "documents_originaux_file": "Documents originaux joints",
    "justificatifs_file": "Justificatif joint",
    "cout_transport": "Coût du transport",
    "frais_transit": "Frais de transit",
    "frais_douane": "Droits de douane",
    "tva": "TVA",
    "livraison_locale": "Coût de livraison locale",
    "autres_frais": "Autres frais",
    "statut": "Phase du dossier",
}


def _history_value(value):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d/%m/%Y à %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if hasattr(value, "name"):
        return Path(value.name).name if value.name else ""
    return str(value)


def business_snapshot(order, *, include_lines=False):
    values = {field: _history_value(getattr(order, field)) for field in BUSINESS_FIELDS}
    responsible = order.responsable
    values["responsable"] = (
        f"{responsible.first_name} {responsible.last_name}".strip() or responsible.email
        if responsible
        else ""
    )
    values["condition_achat"] = CONDITIONS.get(
        order.condition_achat, (order.condition_achat,)
    )[0]
    if include_lines:
        values["lignes"] = "\n".join(
            f"{line.article_reference or line.article_id} : {line.designation} ; "
            f"quantité {line.quantity} ; prix d’achat {line.prix_achat} {line.devise_prix_achat}"
            + (
                f" ; emplacement {line.expected_emplacement}"
                if line.expected_emplacement_id
                else ""
            )
            for line in order.lignes.select_related("expected_emplacement").order_by(
                "id"
            )
        )
    return values


def record_business_changes(order, before, *, user, uploaded_fields=()):
    after = business_snapshot(order, include_lines="lignes" in before)
    recorded = 0
    for field, old_value in before.items():
        new_value = after[field]
        replaced_file = field in uploaded_fields
        if old_value == new_value and not replaced_file:
            continue
        label = BUSINESS_FIELDS.get(field, "Articles de la proforma fournisseur")
        note = "Document remplacé." if replaced_file and old_value == new_value else ""
        if len(old_value) > 255 or len(new_value) > 255:
            note = f"Ancienne valeur :\n{old_value or 'Non renseigné'}\n\nNouvelle valeur :\n{new_value or 'Non renseigné'}"
        order.add_event(
            user=user,
            action=f"Modification : {label}",
            old_value=old_value[:255],
            new_value=new_value[:255],
            note=note,
        )
        recorded += 1
    return recorded
