"""Resolve value start times from recorded dossier events and status snapshots."""

import re

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
        full = re.fullmatch(r"Ancienne valeur :\n([\s\S]*?)\n\nNouvelle valeur :\n([\s\S]*)", event.note)
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
    events = sorted(order.events.all(), key=lambda event: (event.date_created, event.pk))
    status_fields = sorted(set(STATUS_FIELDS.values()))
    snapshots = list(order.history.order_by("history_date", "history_id").values(
        "history_date", "history_type", *status_fields,
    )) if any(event.action in STATUS_FIELDS for event in events) else []
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
        dates[event.pk] = {"before": since, "after": event.date_created if old_value != new_value else since}
        # Saving the same value must not restart its recorded lifetime.
        state[key] = (new_value, event.date_created if old_value != new_value else since)
    return dates
