"""Deletion must conserve the authoritative stock ledger and actor history."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from chat_ai.actions import confirm, prepare
from chat_ai.models import AuditEvent, PendingAction
from chat_ai.tools import ChatAIToolExecutor
from chat_ai_assistant.contracts import ChatAIError
from client.models import Client
from company.models import Company
from facture_client.models import FactureClient
from stock.models import StockMovement, StockReservation
from stock import services
from stock.tests import stock_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def deletion_context(stock_context, settings):
    settings.CHAT_AI_ASSISTANT_ENABLED = True
    role, _ = Role.objects.get_or_create(name='Caissier')
    Membership.objects.create(user=stock_context['user'], company=stock_context['company'], role=role)
    stock_context['creator'] = CustomUser.objects.create_user(email='delivery-creator@example.invalid', password='synthetic-only')
    api = APIClient()
    api.force_authenticate(stock_context['user'])
    stock_context['api'] = api
    return stock_context


def delivery(context, suffix='1', quantity='2.000', status='Accepté', source=None):
    obj = BonDeLivraison.objects.create(
        company=context['company'], client=context['client'],
        numero_bon_livraison='SYN-DELETE-' + suffix,
        date_bon_livraison=date(2026, 10, 8), statut=status,
        created_by_user=context['creator'], source_facture_client=source,
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=obj, article=context['article'], quantity=Decimal(quantity),
        prix_achat=Decimal('10.00'), prix_vente=Decimal('15.00'),
    )
    if status in services.POSTED_DELIVERY_STATUSES:
        services.sync_delivery_stock(obj, 'Envoyé', status, context['user'])
    return obj


def native_delete(context, obj):
    return context['api'].delete(reverse('bon_de_livraison:bon-de-livraison-detail', args=[obj.pk]))


def bulk_delete(context, objects):
    return context['api'].delete(reverse('bon_de_livraison:bon-de-livraison-bulk-delete'),
                                 {'ids': [obj.pk for obj in objects]}, format='json')


def movements(obj):
    return StockMovement.objects.filter(source_type='BonDeLivraison', source_id=obj.pk)


def assert_deleted(context, obj):
    assert not BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert not BonDeLivraisonLine.objects.filter(bon_de_livraison_id=obj.pk).exists()
    history = BonDeLivraison.history.get(id=obj.pk, history_type='-')
    assert history.history_user_id == context['user'].pk
    assert history.created_by_user_id == context['creator'].pk
    assert history.history_user_id != history.created_by_user_id


@pytest.mark.parametrize('status', ['Accepté', 'Facturé'])
@pytest.mark.parametrize('stock_enabled', [True, False])
def test_native_delete_reverses_posted_delivery_once_even_when_stock_disabled(deletion_context, status, stock_enabled):
    c = deletion_context
    obj = delivery(c, status=status)
    original = movements(obj).get(movement_type=StockMovement.TYPE_DELIVERY)
    c['company'].stock_management_enabled = stock_enabled
    c['company'].save(update_fields=['stock_management_enabled'])
    assert native_delete(c, obj).status_code == 204
    assert_deleted(c, obj)
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')
    reversal = movements(obj).get(movement_type=StockMovement.TYPE_REVERSAL)
    assert reversal.reversal_of_id == original.pk
    assert reversal.quantity == -original.quantity
    assert reversal.actor_id == c['user'].pk
    assert native_delete(c, obj).status_code == 404
    assert movements(obj).count() == 2


def test_draft_delete_does_not_create_stock_movements(deletion_context):
    c = deletion_context
    obj = delivery(c, status='Brouillon')
    assert native_delete(c, obj).status_code == 204
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert not movements(obj).exists()
    assert_deleted(c, obj)


def test_previously_reversed_delivery_is_not_reversed_twice(deletion_context):
    c = deletion_context
    obj = delivery(c)
    services.sync_delivery_stock(obj, 'Accepté', 'Annulé', c['user'])
    obj.statut = 'Annulé'
    obj.save(update_fields=['statut'])
    assert native_delete(c, obj).status_code == 204
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).count() == 1


def test_legacy_nonposted_status_still_reverses_existing_posting(deletion_context):
    c = deletion_context
    obj = delivery(c)
    BonDeLivraison.objects.filter(pk=obj.pk).update(statut='Brouillon')
    assert native_delete(c, obj).status_code == 204
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).count() == 1


def test_bulk_delete_reverses_each_delivery_and_preserves_each_actor(deletion_context):
    c = deletion_context
    objects = [delivery(c, suffix=str(index), quantity='1.000') for index in range(2)]
    assert bulk_delete(c, list(reversed(objects))).status_code == 204
    for obj in objects:
        assert_deleted(c, obj)
        assert movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).count() == 1
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')


@pytest.mark.parametrize('bulk', [False, True])
def test_read_only_role_cannot_delete_or_reverse_stock(deletion_context, bulk):
    c = deletion_context
    obj = delivery(c)
    role, _ = Role.objects.get_or_create(name='Lecture')
    Membership.objects.filter(user=c['user'], company=c['company']).update(role=role)
    response = bulk_delete(c, [obj]) if bulk else native_delete(c, obj)
    assert response.status_code == 403
    assert BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')


def test_bulk_authorizes_entire_selection_before_any_reversal(deletion_context):
    c = deletion_context
    obj = delivery(c)
    company = Company.objects.create(raison_sociale='Other synthetic company', ICE='SYN-OTHER-DELETE')
    client = Client.objects.create(company=company, code_client='OTHER-DELETE', client_type='PM', raison_sociale='Other client')
    foreign = BonDeLivraison.objects.create(company=company, client=client,
        numero_bon_livraison='FOREIGN-DELETE', date_bon_livraison=date(2026, 10, 8), created_by_user=c['creator'])
    assert bulk_delete(c, [obj, foreign]).status_code == 403
    assert BonDeLivraison.objects.filter(pk__in=[obj.pk, foreign.pk]).count() == 2
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()


@pytest.mark.parametrize('cancel_proforma', [False, True])
def test_delete_restores_or_releases_consumed_reservation_correctly(deletion_context, cancel_proforma):
    c = deletion_context
    proforma = c['proforma']
    proforma.statut = 'Accepté'
    proforma.save(update_fields=['statut'])
    services.sync_proforma_reservations(proforma, 'Envoyé', 'Accepté')
    invoice = FactureClient.objects.create(company=c['company'], client=c['client'],
        source_proforma=proforma, numero_facture='SYN-DELETE-SOURCE',
        date_facture=date(2026, 10, 8), created_by_user=c['creator'])
    obj = delivery(c, source=invoice)
    if cancel_proforma:
        proforma.statut = 'Annulé'
        proforma.save(update_fields=['statut'])
        services.sync_proforma_reservations(proforma, 'Accepté', 'Annulé')
    assert native_delete(c, obj).status_code == 204
    c['balance'].refresh_from_db()
    reservation = StockReservation.objects.get(proforma_line=c['proforma_line'])
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert reservation.consumed_quantity == Decimal('0.000')
    assert c['balance'].reserved_quantity == Decimal('0.000' if cancel_proforma else '6.000')
    assert reservation.status == ('released' if cancel_proforma else 'active')
    assert reservation.released_quantity == Decimal('6.000' if cancel_proforma else '0.000')


def test_reversal_failure_rolls_back_native_delete(deletion_context, monkeypatch):
    c = deletion_context
    obj = delivery(c)
    original = services.post_movement
    def fail_after_posting(**kwargs):
        original(**kwargs)
        raise ValidationError('Synthetic reversal failure')
    monkeypatch.setattr(services, 'post_movement', fail_after_posting)
    assert native_delete(c, obj).status_code == 400
    assert BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert BonDeLivraisonLine.objects.filter(bon_de_livraison=obj).count() == 1
    assert not BonDeLivraison.history.filter(id=obj.pk, history_type='-').exists()
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')


def test_bulk_failure_restores_already_deleted_delivery_and_all_stock(deletion_context, monkeypatch):
    c = deletion_context
    objects = [delivery(c, suffix=str(index), quantity='1.000') for index in range(2)]
    original = BonDeLivraison.delete
    def fail_second(instance, *args, **kwargs):
        result = original(instance, *args, **kwargs)
        if instance.numero_bon_livraison == objects[1].numero_bon_livraison:
            raise ValidationError('Synthetic second deletion failure')
        return result
    monkeypatch.setattr(BonDeLivraison, 'delete', fail_second)
    assert bulk_delete(c, objects).status_code == 400
    assert BonDeLivraison.objects.filter(pk__in=[obj.pk for obj in objects]).count() == 2
    assert BonDeLivraisonLine.objects.filter(bon_de_livraison_id__in=[obj.pk for obj in objects]).count() == 2
    assert not StockMovement.objects.filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    assert not BonDeLivraison.history.filter(id__in=[obj.pk for obj in objects], history_type='-').exists()
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')


def pending_delete(c, obj):
    executor = ChatAIToolExecutor(c['user'].pk, c['company'].pk, uuid4())
    preview = prepare(executor, 'delivery_note', obj.pk, 'delete')
    return PendingAction.objects.get(pk=preview['action_id'])


def test_assistant_delete_reuses_stock_operation_and_attributes_history(deletion_context):
    c = deletion_context
    obj = delivery(c)
    action = pending_delete(c, obj)
    result = confirm(SimpleNamespace(user=c['user']), action.pk)
    assert result['success'] is True
    assert_deleted(c, obj)
    history = BonDeLivraison.history.get(id=obj.pk, history_type='-')
    assert str(action.pk) in history.history_change_reason
    audit = AuditEvent.objects.get(tool='confirmed_delete', record_id=obj.pk)
    assert audit.actor_id == c['user'].pk and audit.user_id == c['user'].pk
    assert audit.resource == 'delivery_note' and audit.correlation_id == action.pk
    action.refresh_from_db()
    assert action.consumed_at is not None
    with pytest.raises(ChatAIError, match='CONTEXT_EXPIRED'):
        confirm(SimpleNamespace(user=c['user']), action.pk)
    assert movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).count() == 1
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')


@pytest.mark.parametrize('failure', ['reversal', 'deletion', 'audit'])
def test_assistant_failure_rolls_back_stock_document_history_and_confirmation(deletion_context, monkeypatch, failure):
    c = deletion_context
    obj = delivery(c)
    action = pending_delete(c, obj)
    if failure == 'reversal':
        original = services.post_movement
        def fail(**kwargs):
            original(**kwargs)
            raise ValidationError('Synthetic reversal failure')
        monkeypatch.setattr(services, 'post_movement', fail)
    elif failure == 'deletion':
        original = BonDeLivraison.delete
        def fail(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            raise ProtectedError('Synthetic protected record', [])
        monkeypatch.setattr(BonDeLivraison, 'delete', fail)
    else:
        def fail(**kwargs):raise RuntimeError('Synthetic audit persistence failure')
        monkeypatch.setattr(AuditEvent.objects, 'create', fail)
    with pytest.raises(RuntimeError if failure == 'audit' else ChatAIError):
        confirm(SimpleNamespace(user=c['user']), action.pk)
    assert BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert BonDeLivraisonLine.objects.filter(bon_de_livraison=obj).count() == 1
    assert not BonDeLivraison.history.filter(id=obj.pk, history_type='-').exists()
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    assert not AuditEvent.objects.filter(tool='confirmed_delete', record_id=obj.pk).exists()
    action.refresh_from_db()
    assert action.consumed_at is None
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')


def test_multiline_reposted_delivery_reverses_only_unreversed_postings(deletion_context):
    c = deletion_context
    obj = delivery(c, status='Brouillon', quantity='1.000')
    BonDeLivraisonLine.objects.create(bon_de_livraison=obj, article=c['article'],
        quantity=Decimal('1.000'), prix_achat=Decimal('10.00'), prix_vente=Decimal('15.00'))
    services.sync_delivery_stock(obj, 'Brouillon', 'Accepté', c['user'])
    services.sync_delivery_stock(obj, 'Accepté', 'Annulé', c['user'])
    services.sync_delivery_stock(obj, 'Annulé', 'Accepté', c['user'])
    obj.statut = 'Accepté'
    obj.save(update_fields=['statut'])
    assert movements(obj).filter(movement_type=StockMovement.TYPE_DELIVERY).count() == 4
    assert native_delete(c, obj).status_code == 204
    postings = movements(obj).filter(movement_type=StockMovement.TYPE_DELIVERY)
    reversals = movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL)
    assert reversals.count() == 4
    assert set(reversals.values_list('reversal_of_id', flat=True)) == set(postings.values_list('pk', flat=True))
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('4.000')


def test_failed_assistant_delete_restores_consumed_reservation_state(deletion_context, monkeypatch):
    c = deletion_context
    proforma = c['proforma']
    proforma.statut = 'Accepté'
    proforma.save(update_fields=['statut'])
    services.sync_proforma_reservations(proforma, 'Envoyé', 'Accepté')
    invoice = FactureClient.objects.create(company=c['company'], client=c['client'],
        source_proforma=proforma, numero_facture='SYN-DELETE-ROLLBACK',
        date_facture=date(2026, 10, 8), created_by_user=c['creator'])
    obj = delivery(c, source=invoice)
    action = pending_delete(c, obj)
    original = BonDeLivraison.delete
    def fail(instance, *args, **kwargs):
        original(instance, *args, **kwargs)
        raise ProtectedError('Synthetic blocked cascade', [])
    monkeypatch.setattr(BonDeLivraison, 'delete', fail)
    with pytest.raises(ChatAIError, match='ACTION_REJECTED'):
        confirm(SimpleNamespace(user=c['user']), action.pk)
    reservation = StockReservation.objects.get(proforma_line=c['proforma_line'])
    assert reservation.reserved_quantity == Decimal('6.000')
    assert reservation.consumed_quantity == Decimal('2.000')
    assert reservation.released_quantity == Decimal('0.000')
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')
    assert c['balance'].reserved_quantity == Decimal('4.000')
    assert BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    action.refresh_from_db()
    assert action.consumed_at is None


def reserved_delivery(c):
    proforma = c['proforma']
    proforma.statut = 'Accepté'
    proforma.save(update_fields=['statut'])
    services.sync_proforma_reservations(proforma, 'Envoyé', 'Accepté')
    invoice = FactureClient.objects.create(company=c['company'], client=c['client'],
        source_proforma=proforma, numero_facture='SYN-DETACHED-SOURCE',
        date_facture=date(2026, 10, 8), created_by_user=c['creator'])
    return delivery(c, source=invoice), invoice


def test_source_invoice_deletion_keeps_stock_and_reservation_reversal_correct(deletion_context):
    c = deletion_context
    obj, invoice = reserved_delivery(c)
    invoice.delete()
    obj.refresh_from_db()
    assert obj.source_facture_client_id is None
    assert native_delete(c, obj).status_code == 204
    c['balance'].refresh_from_db()
    reservation = StockReservation.objects.get(proforma_line=c['proforma_line'])
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert c['balance'].reserved_quantity == Decimal('6.000')
    assert reservation.consumed_quantity == 0 and reservation.status == 'active'
    assert movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).count() == 1


@pytest.mark.parametrize('link', ['delivery_client', 'balance', 'article', 'emplacement',
                                 'proforma', 'proforma_client', 'reservation_balance'])
def test_inconsistent_company_ledger_is_rejected_before_any_reversal(deletion_context, link):
    from parameter.models import Emplacement
    from stock.models import StockBalance
    c = deletion_context
    obj, _ = reserved_delivery(c)
    foreign = Company.objects.create(raison_sociale='Other synthetic ledger company', ICE='SYN-LEDGER-OTHER')
    foreign_client = Client.objects.create(company=foreign, code_client='SYN-LEDGER-OTHER',
                                           client_type='PM', raison_sociale='Other synthetic ledger client')
    if link == 'delivery_client':
        BonDeLivraison.objects.filter(pk=obj.pk).update(client=foreign_client)
    elif link == 'balance':
        StockBalance.objects.filter(pk=c['balance'].pk).update(company=foreign)
    elif link == 'article':
        type(c['article']).objects.filter(pk=c['article'].pk).update(company=foreign)
    elif link == 'emplacement':
        Emplacement.objects.filter(pk=c['emplacement'].pk).update(company=foreign)
    elif link == 'proforma':
        type(c['proforma']).objects.filter(pk=c['proforma'].pk).update(company=foreign)
    elif link == 'proforma_client':
        type(c['proforma']).objects.filter(pk=c['proforma'].pk).update(client=foreign_client)
    else:
        other_location = Emplacement.objects.create(company=foreign, nom='Foreign synthetic location')
        balance = StockBalance.objects.create(company=foreign, article=c['article'], emplacement=other_location)
        StockReservation.objects.filter(proforma_line=c['proforma_line']).update(balance=balance)
    # Invoke the already-authorized service directly: inconsistent metadata must
    # never mutate another company's stock even if a caller has broad access.
    with pytest.raises(ValidationError):
        services.delete_delivery_with_stock(obj, c['user'])
    c['balance'].refresh_from_db()
    assert c['balance'].physical_quantity == Decimal('2.000')
    assert BonDeLivraison.objects.filter(pk=obj.pk).exists()
    assert not movements(obj).filter(movement_type=StockMovement.TYPE_REVERSAL).exists()
    assert not BonDeLivraison.history.filter(id=obj.pk, history_type='-').exists()


@pytest.mark.django_db(transaction=True)
def test_detached_source_delete_and_proforma_cancellation_complete_without_deadlock(deletion_context, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import close_old_connections, connection, transaction
    c = deletion_context
    with transaction.atomic():
        obj, invoice = reserved_delivery(c)
        invoice.delete()
    proforma_locked, deletion_started, reversal_started = Event(), Event(), Event()
    original_post = services.post_movement
    def signal_reversal(**kwargs):
        if kwargs['movement_type'] == StockMovement.TYPE_REVERSAL:
            reversal_started.set()
        return original_post(**kwargs)
    monkeypatch.setattr(services, 'post_movement', signal_reversal)
    def cancel_proforma():
        close_old_connections()
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '3s'")
                proforma = type(c['proforma']).objects.select_for_update().get(pk=c['proforma'].pk)
                proforma_locked.set()
                assert deletion_started.wait(3)
                # A broken reversal reaches the balance before waiting for this
                # proforma. Correct ordering waits on the proforma first.
                reversal_started.wait(0.3)
                proforma.statut = 'Annulé'
                proforma.save(update_fields=['statut'])
                services.sync_proforma_reservations(proforma, 'Accepté', 'Annulé')
        finally:
            close_old_connections()
    def delete_document():
        close_old_connections()
        try:
            assert proforma_locked.wait(3)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '3s'")
                deletion_started.set()
                services.delete_delivery_with_stock(obj, c['user'])
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(cancel_proforma), pool.submit(delete_document)]
        for future in futures:
            future.result(timeout=8)
    c['balance'].refresh_from_db()
    reservation = StockReservation.objects.get(proforma_line=c['proforma_line'])
    assert c['balance'].physical_quantity == Decimal('4.000')
    assert c['balance'].reserved_quantity == 0
    assert reservation.consumed_quantity == 0 and reservation.released_quantity == Decimal('6.000')
    assert reservation.status == 'released'
    assert not BonDeLivraison.objects.filter(pk=obj.pk).exists()
