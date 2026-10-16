"""History date labels use recorded starts, not the previous unrelated action."""
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.utils.dateparse import parse_datetime

from company.models import Company
from .models import LogisticsOrder
from .serializers import LogisticsOrderEventSerializer

pytestmark = pytest.mark.django_db
T0 = datetime(2026, 9, 14, 9, 32, tzinfo=dt_timezone.utc)
T1, T2, T3, T4 = (T0 + timedelta(minutes=i) for i in range(1, 5))


@pytest.fixture
def order():
    company = Company.objects.create(raison_sociale="History dates", ICE="QA-HISTORY-DATES")
    dossier = LogisticsOrder.objects.create(company=company, numero_commande="QA-HISTORY")
    dossier.history.filter(history_type="+").update(history_date=T0)
    return dossier


def change(order, when, old, new, action="Changement statut Commande & lancement", field="statut_commande_lancement"):
    if field:
        setattr(order, field, new)
        order.save()
        latest = order.history.order_by("-history_date", "-history_id").first()
        order.history.filter(history_id=latest.history_id).update(history_date=when - timedelta(seconds=1))
    event = order.add_event(action=action, old_value=old, new_value=new)
    order.events.filter(pk=event.pk).update(date_created=when)
    event.date_created = when
    return event


def serialized(order):
    return {row["id"]: row for row in LogisticsOrderEventSerializer(order.events.all(), many=True).data}


def since(row):
    return parse_datetime(row["old_value_since"]) if row["old_value_since"] else None


def test_initial_status_uses_recorded_creation_snapshot(order):
    event = change(order, T1, "À lancer", "En cours")
    row = serialized(order)[event.pk]
    assert since(row) == T0
    assert parse_datetime(row["new_value_since"]) == T1


def test_alias_actions_share_status_timeline_and_ignore_unrelated_changes(order):
    first = change(order, T1, "À lancer", "En cours")
    change(order, T2, "Maritime", "Routier", action="Modification : Transport", field=None)
    second = change(order, T3, "En cours", "Terminée", action="Demande de pro forma fournisseur")
    rows = serialized(order)
    assert since(rows[first.pk]) == T0
    assert since(rows[second.pk]) == T1
    assert parse_datetime(rows[second.pk]["new_value_since"]) == T3


def test_missing_history_never_substitutes_creation_or_current_time(order):
    order.history.all().delete()
    event = change(order, T1, "En cours", "Terminée", field=None)
    row = serialized(order)[event.pk]
    assert row["old_value_since"] is None
    assert parse_datetime(row["new_value_since"]) == T1


def test_an_oldest_update_is_not_assumed_to_be_the_initial_start(order):
    order.history.filter(history_type="+").update(history_type="~")
    event = change(order, T1, "À lancer", "En cours")
    assert serialized(order)[event.pk]["old_value_since"] is None


def test_repeated_status_uses_latest_return_to_that_status(order):
    change(order, T1, "À lancer", "En cours")
    change(order, T2, "En cours", "À lancer")
    latest = change(order, T3, "À lancer", "En cours")
    assert since(serialized(order)[latest.pk]) == T2


def test_a_no_op_does_not_reset_the_previous_status_start(order):
    change(order, T1, "À lancer", "En cours")
    unchanged = change(order, T2, "En cours", "En cours")
    row = serialized(order)[unchanged.pk]
    assert parse_datetime(row["new_value_since"]) == since(row) == T1
    latest = change(order, T3, "En cours", "Terminée")
    assert since(serialized(order)[latest.pk]) == T1


def test_new_and_legacy_phase_action_names_share_their_timeline(order):
    first = change(order, T1, "Réception commande", "Proforma", action="Changement de statut", field="statut")
    second = change(order, T2, "Proforma", "Production", action="Modification : Phase du dossier", field="statut")
    rows = serialized(order)
    assert since(rows[first.pk]) == T0
    assert since(rows[second.pk]) == T1


def test_same_value_in_different_status_fields_does_not_share_dates(order):
    change(order, T1, "À lancer", "En cours")
    event = change(order, T2, "À lancer", "En cours", action="Changement de statut global", field="statut_global")
    assert since(serialized(order)[event.pk]) == T0


def test_retained_snapshots_recover_an_unlogged_intermediate_status_change(order):
    change(order, T1, "À lancer", "En cours")
    order.statut_commande_lancement = "Bloquée"
    order.save()
    order.history.filter(history_id=order.history.first().history_id).update(history_date=T2)
    order.statut_commande_lancement = "En cours"
    order.save()
    order.history.filter(history_id=order.history.first().history_id).update(history_date=T3)
    event = change(order, T4, "En cours", "Terminée")
    assert since(serialized(order)[event.pk]) == T3


def test_inconsistent_value_chain_does_not_search_for_an_older_coincidental_match(order):
    change(order, T1, "A", "B", action="Modification : Fournisseur", field=None)
    change(order, T2, "B", "C", action="Modification : Fournisseur", field=None)
    event = change(order, T3, "B", "D", action="Modification : Fournisseur", field=None)
    assert serialized(order)[event.pk]["old_value_since"] is None


def test_full_values_prevent_confusing_different_texts_with_identical_prefixes(order):
    prefix = "a" * 255
    first = change(order, T1, "old", prefix, action="Modification : Fournisseur", field=None)
    first.note = f"Ancienne valeur :\nold\n\nNouvelle valeur :\n{prefix}ONE"
    first.save(update_fields=["note"])
    event = change(order, T2, prefix, "new", action="Modification : Fournisseur", field=None)
    event.note = f"Ancienne valeur :\n{prefix}TWO\n\nNouvelle valeur :\nnew"
    event.save(update_fields=["note"])
    assert serialized(order)[event.pk]["old_value_since"] is None


def test_future_planned_value_keeps_the_actual_recording_time_and_serializing_is_read_only(order):
    event = change(order, T1, "17/10/2026", "20/10/2026", action="Modification : Date d’expédition prévue", field=None)
    before = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    events, snapshots = order.events.count(), order.history.count()
    row = serialized(order)[event.pk]
    assert parse_datetime(row["new_value_since"]) == T1
    assert row["old_value_since"] is None
    assert LogisticsOrder.objects.filter(pk=order.pk).values().get() == before
    assert order.events.count() == events and order.history.count() == snapshots


def test_repeated_value_without_a_known_start_keeps_both_dates_unknown(order):
    order.history.all().delete()
    event = change(order, T1, "En cours", "En cours", field=None)
    row = serialized(order)[event.pk]
    assert row["old_value_since"] is None and row["new_value_since"] is None
