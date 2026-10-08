"""Reopening/retrying confirmations never reexecutes writes or reuses private snapshots."""
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from account.models import Membership, Role
from .actions import confirm
from .confirmation_history import replay_confirmation
from .models import AuditEvent, Message, PendingAction
from .services import ChatAIConversationService, replay_message, stored_action
from .tests import setup, executor, conv

pytestmark = pytest.mark.django_db


def proposal(s, operation='update'):
    args = {'resource': 'invoice', 'identifier': s.invoice.pk, 'operation': operation}
    if operation == 'update':
        args['changes'] = {'remarque': 'Synthetic confirmation note'}
    return executor(s).execute('prepare_change', args)


def saved(s, card, language='fr'):
    conversation = conv(s)
    message = Message.objects.create(conversation=conversation, role='assistant',
                                    action=stored_action({'cards': [card]}, language))
    return conversation, message


def test_saved_confirmation_retains_only_reference_and_reopens_without_new_proposal(setup):
    card = proposal(setup)
    conversation, message = saved(setup, card)
    assert message.action == {'confirmation_id': card['action_id'], 'language': 'fr'}
    before = PendingAction.objects.count()
    with patch('chat_ai.actions.prepare', side_effect=AssertionError('must not create another proposal')):
        reopened = replay_message(executor(setup), message)
    assert reopened['cards'] == [card]
    assert PendingAction.objects.count() == before
    setup.invoice.refresh_from_db()
    assert not setup.invoice.remarque
    assert not AuditEvent.objects.filter(tool__startswith='confirmed_').exists()


@pytest.mark.django_db(transaction=True)
def test_same_request_retry_returns_live_confirmation_without_inference_or_write(setup):
    card = proposal(setup)
    conversation, message = saved(setup, card)
    with patch('chat_ai.services.get_model', side_effect=AssertionError('retry must not infer')):
        result = ChatAIConversationService().run(
            setup.user.pk, conversation.pk, 'Update this note', message.request_id,
            {'interface_language': 'en'}, lambda *_: None, Event())
    assert result['cards'][0]['action_id'] == card['action_id']
    assert PendingAction.objects.count() == 1
    setup.invoice.refresh_from_db()
    assert not setup.invoice.remarque


@pytest.mark.parametrize('operation', ['update', 'delete'])
def test_completed_outcome_survives_pending_purge_and_has_no_record_snapshot(setup, operation):
    card = proposal(setup, operation)
    conversation, message = saved(setup, card, 'en')
    confirm(SimpleNamespace(user=setup.user), card['action_id'])
    PendingAction.objects.filter(pk=card['action_id']).update(expires_at=timezone.now()-timedelta(seconds=1))
    call_command('purge_ai_history')
    assert not PendingAction.objects.filter(pk=card['action_id']).exists()
    api = APIClient(); api.force_authenticate(setup.user)
    result = api.get(f'/api/ai/v1/conversations/{conversation.pk}/')
    assert result.status_code == 200
    status = result.json()['messages'][0]['cards'][0]
    assert set(status) == {'type', 'status', 'message'}
    assert status['type'] == 'confirmation_status' and status['status'] == 'confirmed_' + operation
    assert 'completed' in status['message'] and 'identity' in status['message']
    assert 'Synthetic confirmation note' not in str(result.json())
    assert AuditEvent.objects.filter(tool='confirmed_'+operation).count() == 1


@pytest.mark.parametrize('change,status', [('expired', 'expired'), ('record', 'stale'), ('permission', 'unavailable'), ('moved', 'unavailable')])
def test_changed_or_expired_confirmation_never_replays_values_or_action(setup, change, status):
    card = proposal(setup)
    _, message = saved(setup, card)
    if change == 'expired':
        PendingAction.objects.filter(pk=card['action_id']).update(expires_at=timezone.now()-timedelta(seconds=1))
    elif change == 'record':
        setup.invoice.remarque = 'Changed privately after preview'; setup.invoice.save()
    elif change == 'permission':
        role, _ = Role.objects.get_or_create(name='Lecture')
        setup.membership.role = role; setup.membership.save()
    else:
        type(setup.invoice).objects.filter(pk=setup.invoice.pk).update(company=setup.b)
    result = replay_message(executor(setup), message)['cards'][0]
    assert set(result) == {'type', 'status', 'message'}
    assert result['status'] == status
    assert 'Synthetic confirmation note' not in str(result) and 'Changed privately' not in str(result)


@pytest.mark.parametrize('completed', [False, True])
def test_pending_and_completed_reference_cannot_cross_actor_or_company(setup, completed):
    card = proposal(setup)
    if completed:
        confirm(SimpleNamespace(user=setup.user), card['action_id'])
        PendingAction.objects.filter(pk=card['action_id']).delete()
    Membership.objects.create(user=setup.other, company=setup.a, role=setup.membership.role)
    Membership.objects.create(user=setup.user, company=setup.b, role=setup.membership.role)
    stored = stored_action({'cards': [card]})
    for ex in [executor(setup, user=setup.other), executor(setup, company=setup.b)]:
        result = replay_confirmation(ex, stored)
        assert result['type'] == 'confirmation_status'
        assert result['status'] not in ('confirmed_update', 'confirmed_delete')
        assert set(result) == {'type', 'status', 'message'}


def test_selection_preview_is_persisted_and_reopenable(setup):
    ex = executor(setup); ex.execute('search_invoices', {})
    conversation = conv(setup); conversation.references = ex.state; conversation.save()
    api = APIClient(); api.force_authenticate(setup.user)
    url = f'/api/ai/v1/conversations/{conversation.pk}/'
    response = api.post(url+'selection/', {'resource':'invoice', 'identifier':setup.invoice.pk, 'operation':'delete'}, format='json')
    assert response.status_code == 200
    original = response.json()['cards'][0]
    assert Message.objects.get(conversation=conversation, role='assistant').action['confirmation_id'] == original['action_id']
    history = api.get(url)
    assert history.status_code == 200
    assert history.json()['messages'][1]['cards'] == [original]


def test_selected_edit_navigation_is_preserved_without_executing_edit(setup):
    ex = executor(setup); ex.execute('search_invoices', {})
    conversation = conv(setup); conversation.references = ex.state; conversation.save()
    api = APIClient(); api.force_authenticate(setup.user)
    url = f'/api/ai/v1/conversations/{conversation.pk}/'
    response = api.post(url+'selection/', {'resource':'invoice', 'identifier':setup.invoice.pk, 'operation':'edit'}, format='json')
    assert response.status_code == 200
    history = api.get(url)
    assert history.status_code == 200
    assert history.json()['messages'][1]['cards'] == response.json()['cards']
    assert not PendingAction.objects.exists()


def test_malformed_confirmation_reference_is_nonactionable(setup):
    result = replay_confirmation(executor(setup), {'confirmation_id':'not-a-uuid', 'language':'en'})
    assert result == {'type':'confirmation_status', 'status':'unavailable',
                      'message':'This action is no longer available. Make a new request to continue.'}


@pytest.mark.parametrize('operation', ['edit', 'delete'])
def test_selection_rechecks_record_company_after_tool_before_persisting(setup, operation):
    from .tools import ChatAIToolExecutor
    ex = executor(setup); ex.execute('search_invoices', {})
    conversation = conv(setup); conversation.references = ex.state; conversation.save()
    api = APIClient(); api.force_authenticate(setup.user)
    original = ChatAIToolExecutor.execute

    def moved_after_execute(self, tool, arguments):
        card = original(self, tool, arguments)
        type(setup.invoice).objects.filter(pk=setup.invoice.pk).update(company=setup.b)
        return card

    with patch.object(ChatAIToolExecutor, 'execute', moved_after_execute):
        response = api.post(f'/api/ai/v1/conversations/{conversation.pk}/selection/',
                            {'resource':'invoice', 'identifier':setup.invoice.pk, 'operation':operation}, format='json')
    assert response.status_code in (404, 409)
    assert not Message.objects.filter(conversation=conversation).exists()
    assert 'cards' not in response.json()


def test_pending_preview_rechecks_current_company_form_rules_without_changing_proposal(setup):
    card = proposal(setup)
    _, message = saved(setup, card)
    stored_changes = PendingAction.objects.get(pk=card['action_id']).changes.copy()
    setup.a.raison_sociale = 'IMMOBILIERE NECTAR'; setup.a.save()
    result = replay_message(executor(setup), message)['cards'][0]
    assert set(result) == {'type', 'status', 'message'}
    assert result['status'] == 'unavailable'
    assert PendingAction.objects.get(pk=card['action_id']).changes == stored_changes
    setup.invoice.refresh_from_db()
    assert not setup.invoice.remarque
    assert not AuditEvent.objects.filter(tool__startswith='confirmed_').exists()
