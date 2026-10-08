"""Mutation trust-boundary tests for the three additional document adapters."""
from types import SimpleNamespace
from decimal import Decimal

import pytest
from django.utils import timezone
from account.models import Role
from article.models import Article
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from facture_avoir.models import FactureAvoir, FactureAvoirLine
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import Emplacement, ModePaiement
from stock.models import StockBalance, StockMovement, StockReservation
from chat_ai_assistant.contracts import ChatAIError
from .actions import confirm
from .models import AuditEvent, PendingAction
from .tests import setup, executor, assert_code

pytestmark = pytest.mark.django_db
RESOURCES = ['proforma', 'credit_note', 'delivery_note']


@pytest.fixture
def document_factory(setup):
    def make(resource, status='Brouillon', **extra):
        common = dict(client=setup.client, company=setup.a, created_by_user=setup.user,
                      statut=status, fournisseur='Synthetic Supplier')
        common.update(extra)
        article = Article.objects.get(reference='SYNTH-ITEM')
        line_values = dict(article=article, quantity=1, prix_achat=80, prix_vente=100)
        if resource == 'proforma':
            document = FactureProForma.objects.create(
                numero_facture='P900/26', date_facture=timezone.localdate(), **common)
            FactureProFormaLine.objects.create(facture_pro_forma=document, **line_values)
        elif resource == 'credit_note':
            document = FactureAvoir.objects.create(
                numero_avoir='AV900/26', date_avoir=timezone.localdate(),
                facture_origine=setup.invoice, motif_avoir='remise', **common)
            FactureAvoirLine.objects.create(facture_avoir=document, **line_values)
        else:
            document = BonDeLivraison.objects.create(
                numero_bon_livraison='0900/26', date_bon_livraison=timezone.localdate(), **common)
            BonDeLivraisonLine.objects.create(bon_de_livraison=document, **line_values)
        document.refresh_from_db()
        return document
    return make


def state(document):
    return {field.attname: getattr(document, field.attname) for field in document._meta.concrete_fields
            if field.name not in ('remarque', 'date_updated')}


def proposal(s, document, resource, operation='update'):
    args = {'resource': resource, 'identifier': document.pk, 'operation': operation}
    if operation == 'update':
        args['changes'] = {'remarque': 'Approved synthetic note'}
    return executor(s).execute('prepare_change', args)


@pytest.mark.parametrize('resource', RESOURCES)
def test_confirmed_remark_preserves_other_fields_lines_and_human_history(setup, document_factory, resource):
    document = document_factory(resource)
    before = state(document)
    lines = list(document.lignes.values())
    card = proposal(setup, document, resource)
    document.refresh_from_db()
    assert not document.remarque
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    document.refresh_from_db()
    assert document.remarque == 'Approved synthetic note'
    assert state(document) == before and list(document.lignes.values()) == lines
    historical = document.history.first()
    assert historical.history_user_id == setup.user.pk
    assert str(card['action_id']) in historical.history_change_reason
    audit = AuditEvent.objects.get(tool='confirmed_update')
    assert (audit.actor_id, audit.resource, audit.record_id, audit.changed_fields) == (
        setup.user.pk, resource, document.pk, ['remarque'])
    assert_code('CONTEXT_EXPIRED', lambda: confirm(SimpleNamespace(user=setup.user), card['action_id']))


@pytest.mark.parametrize('resource', RESOURCES)
def test_confirmed_delete_preserves_human_attribution(setup, document_factory, resource):
    document = document_factory(resource)
    record_id = document.pk
    card = proposal(setup, document, resource, 'delete')
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    assert not type(document).objects.filter(pk=record_id).exists()
    historical = type(document).history.filter(id=record_id, history_type='-').first()
    assert historical.history_user_id == setup.user.pk
    audit = AuditEvent.objects.get(tool='confirmed_delete')
    assert (audit.actor_id, audit.resource, audit.record_id) == (setup.user.pk, resource, record_id)
    assert audit.instruction_id == PendingAction.objects.get(pk=card['action_id']).instruction_id


@pytest.mark.parametrize('resource', RESOURCES)
@pytest.mark.parametrize('role,operation,allowed', [
    ('Lecture', 'update', False), ('Comptable', 'delete', False),
    ('Commercial', 'update', True), ('Commercial', 'delete', False),
])
def test_added_document_actions_use_existing_role_permissions(setup, document_factory, resource, role, operation, allowed):
    document = document_factory(resource)
    changed_role, _ = Role.objects.get_or_create(name=role)
    setup.membership.role = changed_role
    setup.membership.save(update_fields=['role'])
    if allowed:
        assert proposal(setup, document, resource, operation)['type'] == 'confirmation'
    else:
        assert_code('PERMISSION_DENIED', lambda: proposal(setup, document, resource, operation))
    document.refresh_from_db()
    assert not document.remarque


@pytest.mark.parametrize('resource', RESOURCES)
def test_confirmation_rechecks_revoked_write_permission(setup, document_factory, resource):
    document = document_factory(resource)
    card = proposal(setup, document, resource)
    readonly, _ = Role.objects.get_or_create(name='Lecture')
    setup.membership.role = readonly
    setup.membership.save(update_fields=['role'])
    assert_code('PERMISSION_DENIED', lambda: confirm(SimpleNamespace(user=setup.user), card['action_id']))
    document.refresh_from_db()
    assert not document.remarque and not AuditEvent.objects.filter(tool='confirmed_update').exists()
    assert PendingAction.objects.get(pk=card['action_id']).consumed_at is None


@pytest.mark.parametrize('resource', RESOURCES)
def test_actions_reject_moved_company_records_and_unapproved_fields(setup, document_factory, resource):
    document = document_factory(resource)
    for changes in ({'statut': 'Accepté'}, {'total_ttc_apres_remise': '0'}, {'company': setup.b.pk}, {'lignes': []}):
        assert_code('INVALID_ARGUMENTS', lambda: executor(setup).execute('prepare_change', {
            'resource': resource, 'identifier': document.pk, 'operation': 'update', 'changes': changes,
        }))
    type(document).objects.filter(pk=document.pk).update(company=setup.b)
    assert_code('NOT_FOUND', lambda: proposal(setup, document, resource))


@pytest.mark.parametrize('status', ['Envoyé', 'Accepté', 'Annulé'])
def test_credit_remark_update_keeps_existing_draft_only_restriction(setup, document_factory, status):
    document = document_factory('credit_note', status=status)
    assert_code('INVALID_ARGUMENTS', lambda: proposal(setup, document, 'credit_note'))
    assert not PendingAction.objects.exists()


def test_credit_remark_keeps_own_payment_mode_currency_and_origin(setup, document_factory):
    origin_mode = ModePaiement.objects.create(company=setup.a, nom='Origin payment mode')
    credit_mode = ModePaiement.objects.create(company=setup.a, nom='Credit payment mode')
    setup.invoice.mode_paiement = origin_mode
    setup.invoice.save(update_fields=['mode_paiement'])
    document = document_factory('credit_note', mode_paiement=credit_mode, devise='EUR')
    before = state(document)
    card = proposal(setup, document, 'credit_note')
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    document.refresh_from_db()
    assert state(document) == before
    assert document.mode_paiement_id == credit_mode.pk and document.devise == 'EUR'


@pytest.mark.parametrize('timing', ['before_preview', 'after_preview'])
def test_credit_remark_never_silently_fills_an_inherited_payment_mode(setup, document_factory, timing):
    document = document_factory('credit_note')
    assert document.mode_paiement_id is None
    before = state(document)
    card = proposal(setup, document, 'credit_note') if timing == 'after_preview' else None
    # An ordinary later origin edit creates this state without corrupting records.
    setup.invoice.mode_paiement = ModePaiement.objects.create(company=setup.a, nom='Later origin payment mode')
    setup.invoice.save(update_fields=['mode_paiement'])
    if card is None:
        assert_code('ACTION_REJECTED', lambda: proposal(setup, document, 'credit_note'))
        assert not PendingAction.objects.exists()
    else:
        assert_code('ACTION_REJECTED', lambda: confirm(SimpleNamespace(user=setup.user), card['action_id']))
        assert PendingAction.objects.get(pk=card['action_id']).consumed_at is None
    document.refresh_from_db()
    assert state(document) == before
    assert not AuditEvent.objects.filter(tool='confirmed_update').exists()


@pytest.mark.parametrize('status', ['active', 'released'])
def test_proforma_stock_reservation_blocks_delete_without_consuming_confirmation(setup, document_factory, status):
    document = document_factory('proforma')
    line = document.lignes.get()
    location = Emplacement.objects.create(company=setup.a, nom='Synthetic stock location')
    balance = StockBalance.objects.create(company=setup.a, article=line.article, emplacement=location,
                                         physical_quantity=10, reserved_quantity=1 if status == 'active' else 0)
    reservation = StockReservation.objects.create(proforma_line=line, balance=balance, reserved_quantity=1, status=status)
    card = proposal(setup, document, 'proforma', 'delete')
    assert_code('ACTION_REJECTED', lambda: confirm(SimpleNamespace(user=setup.user), card['action_id']))
    assert FactureProForma.objects.filter(pk=document.pk).exists()
    assert StockReservation.objects.filter(pk=reservation.pk).exists()
    assert PendingAction.objects.get(pk=card['action_id']).consumed_at is None
    assert not AuditEvent.objects.filter(tool='confirmed_delete').exists()


def test_accepted_delivery_remark_does_not_repeat_stock_movement(setup, document_factory):
    document = document_factory('delivery_note', status='Accepté')
    line = document.lignes.get()
    location = Emplacement.objects.create(company=setup.a, nom='Synthetic delivery location')
    balance = StockBalance.objects.create(company=setup.a, article=line.article, emplacement=location,
                                         physical_quantity=9, reserved_quantity=0)
    movement = StockMovement.objects.create(balance=balance, movement_type='delivery', quantity=-1,
                                           balance_after=9, source_type='bon_de_livraison', source_id=document.pk,
                                           source_line_id=line.pk, actor=setup.user)
    card = proposal(setup, document, 'delivery_note')
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    balance.refresh_from_db()
    assert balance.physical_quantity == Decimal('9') and balance.reserved_quantity == Decimal('0')
    assert list(StockMovement.objects.values_list('pk', flat=True)) == [movement.pk]
    document.refresh_from_db()
    assert document.statut == 'Accepté'


def test_accepted_proforma_remark_preserves_reserved_stock(setup, document_factory):
    document = document_factory('proforma', status='Accepté')
    line = document.lignes.get()
    location = Emplacement.objects.create(company=setup.a, nom='Synthetic reserved location')
    balance = StockBalance.objects.create(company=setup.a, article=line.article, emplacement=location,
                                         physical_quantity=10, reserved_quantity=1)
    reservation = StockReservation.objects.create(proforma_line=line, balance=balance,
                                                  reserved_quantity=1, status='active')
    before = StockReservation.objects.values().get(pk=reservation.pk)
    card = proposal(setup, document, 'proforma')
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    balance.refresh_from_db()
    document.refresh_from_db()
    assert balance.physical_quantity == Decimal('10') and balance.reserved_quantity == Decimal('1')
    assert StockReservation.objects.values().get(pk=reservation.pk) == before
    assert document.statut == 'Accepté' and document.remarque == 'Approved synthetic note'


@pytest.fixture
def editable_document(setup, document_factory):
    def make(resource):
        if resource == 'invoice':
            return setup.invoice
        if resource == 'quote':
            from devi.models import Devi
            return Devi.objects.create(company=setup.a, client=setup.client,
                numero_devis='SYNTH-NORMALIZATION', date_devis=timezone.localdate(),
                created_by_user=setup.user)
        return document_factory(resource)
    return make


@pytest.mark.parametrize('resource', ['invoice', 'quote', *RESOURCES])
def test_native_nectar_hidden_remark_has_no_misleading_preview(setup, editable_document, resource):
    document = editable_document(resource)
    setup.a.raison_sociale = 'IMMOBILIERE NECTAR'
    setup.a.save(update_fields=['raison_sociale'])
    assert_code('ACTION_REJECTED', lambda: proposal(setup, document, resource))
    assert not PendingAction.objects.exists()
    document.refresh_from_db()
    assert not document.remarque


@pytest.mark.parametrize('resource', ['invoice', 'quote', *RESOURCES])
def test_company_rule_change_rechecked_before_consuming_confirmation(setup, editable_document, resource):
    document = editable_document(resource)
    card = proposal(setup, document, resource)
    setup.a.raison_sociale = 'IMMOBILIERE NECTAR'
    setup.a.save(update_fields=['raison_sociale'])
    assert_code('ACTION_REJECTED', lambda: confirm(SimpleNamespace(user=setup.user), card['action_id']))
    assert PendingAction.objects.get(pk=card['action_id']).consumed_at is None
    assert not AuditEvent.objects.filter(tool='confirmed_update').exists()
    document.refresh_from_db()
    assert not document.remarque


def test_native_whitespace_normalization_is_shown_in_preview_and_audit(setup):
    card = executor(setup).execute('prepare_change', {
        'resource': 'invoice', 'identifier': setup.invoice.pk, 'operation': 'update',
        'changes': {'remarque': '  Synthetic trimmed remark  ', 'date_echeance': None},
    })
    assert card['changes'] == {'remarque': 'Synthetic trimmed remark'}
    assert PendingAction.objects.get(pk=card['action_id']).changes == card['changes']
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    setup.invoice.refresh_from_db()
    assert setup.invoice.remarque == card['changes']['remarque']
    assert AuditEvent.objects.get(tool='confirmed_update').changed_fields == ['remarque']


def test_nectar_visible_due_date_edit_stays_available_without_hidden_side_effects(setup):
    setup.a.raison_sociale = 'IMMOBILIERE NECTAR'
    setup.a.save(update_fields=['raison_sociale'])
    card = executor(setup).execute('prepare_change', {
        'resource': 'invoice', 'identifier': setup.invoice.pk, 'operation': 'update',
        'changes': {'date_echeance': '2027-02-18'},
    })
    assert card['changes'] == {'date_echeance': '2027-02-18'}
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    setup.invoice.refresh_from_db()
    assert setup.invoice.date_echeance.isoformat() == '2027-02-18'
    assert AuditEvent.objects.get(tool='confirmed_update').changed_fields == ['date_echeance']


def test_native_unrequested_financial_normalization_cannot_hide_in_due_date_preview(setup):
    setup.a.raison_sociale = 'IMMOBILIERE NECTAR'
    setup.a.save(update_fields=['raison_sociale'])
    type(setup.invoice).objects.filter(pk=setup.invoice.pk).update(remise=10, remise_type='%')
    assert_code('ACTION_REJECTED', lambda: executor(setup).execute('prepare_change', {
        'resource': 'invoice', 'identifier': setup.invoice.pk, 'operation': 'update',
        'changes': {'date_echeance': '2027-02-18'},
    }))
    assert not PendingAction.objects.exists()
    setup.invoice.refresh_from_db()
    assert setup.invoice.remise == 10 and setup.invoice.date_echeance is None
