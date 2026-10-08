"""Synthetic database contracts for bounded, read-only operational adapters."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import json
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from account.models import CustomUser, Role
from article.models import Article
from client.models import Client
from facture_proforma.models import FactureProForma, FactureProFormaLine
from logistique.models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma
from parameter.models import Emplacement
from stock.models import StockBalance, StockMovement, StockReceipt, StockReceiptLine, InventorySession, InventoryLine
from stock.services import prepare_balance_snapshots
from . import operations
from .tests import setup, executor, assert_code

pytestmark = pytest.mark.django_db
RESOURCES = tuple(operations.OPERATIONS)


@pytest.fixture
def records(setup):
    article = Article.objects.get(company=setup.a, reference='SYNTH-ITEM')
    article.stock_minimum = Decimal('2')
    article.save()
    location = Emplacement.objects.create(company=setup.a, nom='Dépôt تجريبي')
    foreign_location = Emplacement.objects.create(company=setup.b, nom='SECRET_LOCATION')
    foreign_article = Article.objects.create(company=setup.b, reference='SECRET_PRODUCT',
        designation='SECRET_DESIGNATION', prix_achat=1, prix_vente=2, tva=0)
    proforma = FactureProForma.objects.create(client=setup.client, numero_facture='OPS-PF/26',
        date_facture=date(2026, 3, 1), created_by_user=setup.user)
    source = FactureProFormaLine.objects.create(facture_pro_forma=proforma, article=article,
        quantity=6, prix_achat=80, prix_vente=100)
    foreign_proforma = FactureProForma.objects.create(client=setup.restricted.client,
        numero_facture='SECRET_PF/26', date_facture=date(2026, 3, 1), created_by_user=setup.other)
    foreign_source = FactureProFormaLine.objects.create(facture_pro_forma=foreign_proforma,
        article=foreign_article, quantity=8, prix_achat=1, prix_vente=2)
    order = LogisticsOrder.objects.create(company=setup.a, numero_commande='LOG-OPS',
        fournisseur='Fournisseur تجريبي', statut='Production', statut_commande_lancement='Terminée',
        created_by_user=setup.user, description='SECRET_NOTE', fournisseur_email='secret@example.invalid')
    link = LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)
    line = LogisticsOrderLine.objects.create(commande=order, proforma=proforma, source_line=source,
        article=article, client=setup.client, expected_emplacement=location,
        quantity=6, received_quantity=2, prix_achat=80, prix_vente=100)
    foreign_order = LogisticsOrder.objects.create(company=setup.b, numero_commande='SECRET_ORDER',
        fournisseur='SECRET_SUPPLIER', created_by_user=setup.other)
    balance = StockBalance.objects.create(company=setup.a, article=article, emplacement=location,
        physical_quantity=4, reserved_quantity=1)
    movement = StockMovement.objects.create(balance=balance, movement_type='opening', quantity=4,
        balance_after=4, note='SECRET_NOTE', actor=setup.user, source_id=424242)
    receipt = StockReceipt.objects.create(company=setup.a, logistics_order=order, reference='REC-OPS',
        created_by=setup.user, note='SECRET_NOTE')
    receipt_line = StockReceiptLine.objects.create(receipt=receipt, logistics_line=line, article=article,
        emplacement=location, quantity=2)
    inventory = InventorySession.objects.create(company=setup.a, emplacement=location,
        reference='INV-OPS', created_by=setup.user, note='SECRET_NOTE')
    inventory_line = InventoryLine.objects.create(inventory=inventory, article=article,
        expected_quantity=4, counted_quantity=5)
    return SimpleNamespace(article=article, location=location, foreign_article=foreign_article,
        foreign_location=foreign_location, proforma=proforma, source=source,
        foreign_proforma=foreign_proforma, foreign_source=foreign_source, order=order,
        foreign_order=foreign_order, link=link, line=line, balance=balance, movement=movement,
        receipt=receipt, receipt_line=receipt_line, inventory=inventory, inventory_line=inventory_line,
        objects={'stock_balance': balance, 'stock_movement': movement, 'stock_receipt': receipt,
                 'stock_inventory': inventory, 'logistics_order': order})


@pytest.mark.parametrize('resource', RESOURCES)
def test_search_detail_are_minimal_scoped_and_read_only(setup, records, resource):
    ex = executor(setup)
    obj = records.objects[resource]
    with CaptureQueriesContext(connection) as captured:
        listed = operations.search(ex, resource)
        detailed = operations.detail(ex, resource, obj.pk)
    assert [item['id'] for item in listed['items']] == [obj.pk]
    item, = detailed['items']
    assert item['navigation']['path'] == f'{operations.OPERATIONS[resource].route}{obj.pk}/?company_id={setup.a.pk}'
    assert ex.state['resource'] == resource and ex.state['ids'] == [obj.pk]
    payload = json.dumps([listed, detailed])
    assert not any(term in payload for term in ['SECRET_', 'secret@example', '424242', 'prix_', 'created_by', 'note'])
    assert not any(re.match(r'\s*(INSERT|UPDATE|DELETE|ALTER|CREATE)\b', q['sql'], re.I) for q in captured)
    assert 'count' not in listed


def test_balance_snapshot_reuses_existing_authoritative_calculation(setup, records, monkeypatch):
    records.balance.refresh_from_db()
    expected = prepare_balance_snapshots([records.balance])[records.balance.pk]
    original = operations.prepare_balance_snapshots
    called = []
    def observed(balances):
        balances = list(balances)
        called.append([balance.pk for balance in balances])
        return original(balances)
    monkeypatch.setattr(operations, 'prepare_balance_snapshots', observed)
    item, = operations.search(executor(setup), 'stock_balance')['items']
    assert called == [[records.balance.pk]]
    for key, value in expected.items():
        assert item['status' if key == 'stock_state' else key] == (value if key == 'stock_state' else str(value))
    assert Decimal(item['incoming_quantity']) == 4
    assert Decimal(item['projected_quantity']) == 7


def test_logistics_status_uses_calculation_without_sync_or_save(setup, records, monkeypatch):
    LogisticsOrder.objects.filter(pk=records.order.pk).update(statut_global='Brouillon')
    records.order.refresh_from_db()
    expected = records.order.calculate_global_status()
    assert expected != 'Brouillon'
    def forbidden(*args, **kwargs):
        raise AssertionError('Operational reads must never synchronize or save')
    monkeypatch.setattr(LogisticsOrder, 'sync_global_status', forbidden)
    monkeypatch.setattr(LogisticsOrder, 'save', forbidden)
    item, = operations.detail(executor(setup), 'logistics_order', records.order.pk)['items']
    assert item['global_status'] == expected
    records.order.refresh_from_db()
    assert records.order.statut_global == 'Brouillon'


@pytest.mark.parametrize('resource', RESOURCES)
def test_natural_product_location_and_reference_search(setup, records, resource):
    obj = records.objects[resource]
    reference = {'stock_balance': records.article.reference, 'stock_movement': records.article.reference,
        'stock_receipt': records.receipt.reference, 'stock_inventory': records.inventory.reference,
        'logistics_order': records.order.numero_commande}[resource]
    args = dict(reference=reference, product_name='Synthetic', location_name='تجريبي')
    if resource in ('logistics_order', 'stock_receipt'):
        args.update(client_name='Démo', supplier_name='Fournisseur')
    assert [i['id'] for i in operations.search(executor(setup), resource, **args)['items']] == [obj.pk]
    args['product_name'] = 'not-present'
    assert not operations.search(executor(setup), resource, **args)['items']


@pytest.mark.parametrize('resource', ['logistics_order', 'stock_receipt'])
def test_client_and_product_must_match_same_line(setup, records, resource):
    other_client = Client.objects.create(company=setup.a, code_client='LINE-OTHER', client_type='PM', raison_sociale='Different Client')
    other_product = Article.objects.create(company=setup.a, reference='OTHER-PRODUCT', designation='Other product', prix_achat=1, prix_vente=2, tva=0)
    proforma = FactureProForma.objects.create(client=other_client, numero_facture='OTHER/26', date_facture=date(2026, 3, 1), created_by_user=setup.user)
    line = LogisticsOrderLine.objects.create(commande=records.order, proforma=proforma, article=other_product,
        client=other_client, quantity=1, prix_achat=1, prix_vente=2, expected_emplacement=records.location)
    StockReceiptLine.objects.create(receipt=records.receipt, logistics_line=line, article=other_product,
        emplacement=records.location, quantity=1)
    assert not operations.search(executor(setup), resource, product_name='OTHER-PRODUCT', client_name='Démo')['items']


@pytest.mark.parametrize('role', ['Lecture', 'Comptable', 'Commercial', 'Logistique'])
@pytest.mark.parametrize('resource', RESOURCES)
def test_existing_member_roles_can_read_without_invented_gates(setup, records, role, resource):
    setup.membership.role, _ = Role.objects.get_or_create(name=role)
    setup.membership.save()
    assert operations.search(executor(setup), resource)['items']


@pytest.mark.parametrize('resource', RESOURCES)
def test_authorization_refreshes_membership_before_and_after_data(setup, records, resource, monkeypatch):
    original = operations.card
    def revoked(*args, **kwargs):
        result = original(*args, **kwargs)
        setup.membership.delete()
        return result
    monkeypatch.setattr(operations, 'card', revoked)
    assert_code('PERMISSION_DENIED', lambda: operations.search(executor(setup), resource))
    assert_code('PERMISSION_DENIED', lambda: operations.detail(executor(setup), resource, records.objects[resource].pk))


@pytest.mark.parametrize('resource', RESOURCES)
def test_native_superuser_policy_is_resource_specific(setup, records, resource):
    setup.membership.delete()
    CustomUser.objects.filter(pk=setup.user.pk).update(is_superuser=True)
    if resource.startswith('stock_'):
        assert operations.search(executor(setup), resource)['items']
    else:
        assert_code('PERMISSION_DENIED', lambda: operations.search(executor(setup), resource))


@pytest.mark.parametrize('resource', RESOURCES)
def test_staff_alone_is_not_company_access(setup, records, resource):
    setup.membership.delete()
    CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=True)
    assert_code('PERMISSION_DENIED', lambda: operations.search(executor(setup), resource))


@pytest.mark.parametrize('resource', RESOURCES)
def test_foreign_or_missing_identifiers_have_same_error(setup, records, resource):
    obj = records.objects[resource]
    assert_code('NOT_FOUND', lambda: operations.detail(executor(setup, user=setup.other, company=setup.b), resource, obj.pk))
    assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), resource, 2147483647))


@pytest.mark.parametrize('kind', ['inactive', 'feature'])
def test_user_and_feature_rechecked(setup, records, settings, kind):
    if kind == 'inactive':
        CustomUser.objects.filter(pk=setup.user.pk).update(is_active=False)
    else:
        settings.CHAT_AI_ASSISTANT_ENABLED = False
    assert_code('NOT_AUTHENTICATED' if kind == 'inactive' else 'APPLICATION_UNAVAILABLE',
                lambda: operations.search(executor(setup), 'stock_balance'))


@pytest.mark.parametrize('args', [
    {'company_id': 2}, {'order_by': 'client__email'}, {'limit': True}, {'limit': 0}, {'limit': 11},
    {'offset': -1}, {'offset': 1001}, {'offset': False}, {'reference': 'x' * 121},
    {'reference': '\x00'}, {'product_name': ['x']}, {'status': 'administrator'},
    {'date_from': '2026-02-30'}, {'date_to': 'today'}, {'date_from': '2026-4-1'},
    {'date_from': '2026-04-01', 'date_to': '2026-03-01'}, {'date_from': '2000-01-01', 'date_to': '2026-01-01'},
    {'client_name': 'not a balance filter'},
])
def test_strict_fixed_arguments(setup, args):
    assert_code('INVALID_ARGUMENTS', lambda: operations.search(executor(setup), 'stock_balance', **args))


@pytest.mark.parametrize('resource', ['__dict__', 'sql', 'management_projet', None, {}])
def test_unknown_resources_rejected(setup, resource):
    assert_code('INVALID_ARGUMENTS', lambda: operations.search(executor(setup), resource))


@pytest.mark.parametrize('identifier', [True, 0, -1, '1', 2147483648])
def test_detail_identifiers_are_strict(setup, identifier):
    assert_code('INVALID_ARGUMENTS', lambda: operations.detail(executor(setup), 'stock_balance', identifier))


@pytest.mark.parametrize('field', ['client', 'proforma', 'article', 'expected_emplacement', 'source_line'])
def test_inconsistent_logistics_lines_hide_order_and_dependent_receipts(setup, records, field):
    values = {'client': setup.restricted.client, 'proforma': records.foreign_proforma,
        'article': records.foreign_article, 'expected_emplacement': records.foreign_location,
        'source_line': records.foreign_source}
    LogisticsOrderLine.objects.filter(pk=records.line.pk).update(**{field: values[field]})
    for resource in ('logistics_order', 'stock_receipt'):
        assert not operations.search(executor(setup), resource)['items']
        assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), resource, records.objects[resource].pk))


def test_nullable_logistics_source_and_location_are_legitimate(setup, records):
    LogisticsOrderLine.objects.filter(pk=records.line.pk).update(source_line=None, expected_emplacement=None)
    assert operations.detail(executor(setup), 'logistics_order', records.order.pk)['items'][0]['lines'][0]['location'] is None


def test_foreign_proforma_link_hides_order_even_without_foreign_lines(setup, records):
    LogisticsOrderProforma.objects.create(commande=records.order, proforma=records.foreign_proforma)
    assert not operations.search(executor(setup), 'logistics_order')['items']
    assert not operations.search(executor(setup), 'stock_receipt')['items']
    assert not operations.search(executor(setup), 'stock_balance')['items']


def test_inconsistent_incoming_quantity_never_leaks_via_balance_summary(setup, records):
    LogisticsOrderLine.objects.filter(pk=records.line.pk).update(client=setup.restricted.client)
    assert not operations.search(executor(setup), 'stock_balance')['items']
    assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), 'stock_balance', records.balance.pk))
    # An excluded incoming stage must not suppress unrelated valid physical stock.
    LogisticsOrder.objects.filter(pk=records.order.pk).update(statut='Clôture')
    assert Decimal(operations.search(executor(setup), 'stock_balance')['items'][0]['incoming_quantity']) == 0


@pytest.mark.parametrize('field', ['article', 'emplacement'])
def test_balance_related_company_mismatch_also_hides_movements(setup, records, field):
    StockBalance.objects.filter(pk=records.balance.pk).update(**{field: getattr(records, 'foreign_' + ('location' if field == 'emplacement' else field))})
    for resource in ('stock_balance', 'stock_movement'):
        assert not operations.search(executor(setup), resource)['items']
        assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), resource, records.objects[resource].pk))


@pytest.mark.parametrize('kind', ['article', 'location', 'order', 'line_order', 'line_article'])
def test_receipt_inconsistent_relations_are_never_projected(setup, records, kind):
    if kind == 'order':
        StockReceipt.objects.filter(pk=records.receipt.pk).update(logistics_order=records.foreign_order)
    elif kind == 'line_order':
        other = LogisticsOrder.objects.create(company=setup.a, numero_commande='OTHER-ORDER')
        LogisticsOrderLine.objects.filter(pk=records.line.pk).update(commande=other)
    else:
        article = records.foreign_article
        if kind == 'line_article':
            article = Article.objects.create(company=setup.a, reference='MISMATCH', designation='Other own product', prix_achat=1, prix_vente=2, tva=0)
        StockReceiptLine.objects.filter(pk=records.receipt_line.pk).update(**(
            {'emplacement': records.foreign_location} if kind == 'location' else {'article': article}))
    assert not operations.search(executor(setup), 'stock_receipt')['items']
    assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), 'stock_receipt', records.receipt.pk))


@pytest.mark.parametrize('kind', ['location', 'article'])
def test_inventory_inconsistent_relations_are_never_projected(setup, records, kind):
    if kind == 'location':
        InventorySession.objects.filter(pk=records.inventory.pk).update(emplacement=records.foreign_location)
    else:
        InventoryLine.objects.filter(pk=records.inventory_line.pk).update(article=records.foreign_article)
    assert not operations.search(executor(setup), 'stock_inventory')['items']
    assert_code('NOT_FOUND', lambda: operations.detail(executor(setup), 'stock_inventory', records.inventory.pk))


@pytest.mark.parametrize('physical,reserved,status', [(1, 3, 'a_approvisionner'), (2, 1, 'minimum'), (4, 1, 'disponible')])
def test_stock_state_search_matches_snapshot(setup, records, physical, reserved, status):
    StockBalance.objects.filter(pk=records.balance.pk).update(physical_quantity=physical, reserved_quantity=reserved)
    for candidate in operations.OPERATIONS['stock_balance'].statuses:
        items = operations.search(executor(setup), 'stock_balance', status=candidate)['items']
        assert bool(items) is (candidate == status)
        if items:
            assert items[0]['status'] == status


def test_search_pagination_and_detail_line_bounds(setup, records):
    for index in range(12):
        InventorySession.objects.create(company=setup.a, emplacement=records.location,
            reference=f'PAGE-{index}', created_by=setup.user)
        article = Article.objects.create(company=setup.a, reference=f'LINE-{index}', designation='Line', prix_achat=1, prix_vente=2, tva=0)
        InventoryLine.objects.create(inventory=records.inventory, article=article, expected_quantity=0, counted_quantity=index)
    first = operations.search(executor(setup), 'stock_inventory')
    second = operations.search(executor(setup), 'stock_inventory', offset=10)
    assert len(first['items']) == 10 and first['has_more'] and first['next_offset'] == 10
    assert len(second['items']) == 3 and not second['has_more'] and second['next_offset'] is None
    assert not set(i['id'] for i in first['items']) & set(i['id'] for i in second['items'])
    item, = operations.detail(executor(setup), 'stock_inventory', records.inventory.pk)['items']
    assert len(item['lines']) == 10 and item['has_more_lines'] is True


def test_dates_use_application_timezone_and_plain_sql_text_is_only_a_filter(setup, records):
    today = timezone.localdate().isoformat()
    assert operations.search(executor(setup), 'stock_movement', date_from=today, date_to=today)['items']
    assert not operations.search(executor(setup), 'stock_movement', reference="' OR 1=1 --")['items']
    assert StockMovement.objects.filter(pk=records.movement.pk).exists()
