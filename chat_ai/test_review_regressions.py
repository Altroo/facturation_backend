"""Regression coverage for independently reviewed history/planner trust boundaries."""
import json
from threading import Event
from unittest.mock import Mock
import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient

from chat_ai_assistant.clarifications import MESSAGES
from chat_ai_assistant.contracts import ChatAIError
from chat_ai_assistant.provider import ChatAIModelService, ModelConfig
from .models import KnowledgeDocument, Message
from .services import ChatAIConversationService, stored_action
from .tests import setup, conv, executor
from .tools import registry
from .views import ChatReadThrottle


@pytest.fixture
def history_access(monkeypatch):
    # Service replay must not close pytest's surrounding transaction.
    monkeypatch.setattr('chat_ai.services.close_old_connections', lambda: None)
    model = Mock(side_effect=AssertionError('History replay must not invoke a model'))
    monkeypatch.setattr('chat_ai.services.get_model', model)
    monkeypatch.setattr(ChatReadThrottle, 'cache', LocMemCache(str(uuid.uuid4()), {}))

    def read(s, conversation, assistant, path):
        if path == 'history':
            api = APIClient()
            api.force_authenticate(s.user)
            response = api.get(f'/api/ai/v1/conversations/{conversation.pk}/')
            assert response.status_code == 200
            return next(message for message in response.json()['messages'] if message['id'] == str(assistant.pk))
        return ChatAIConversationService().run(
            s.user.pk, conversation.pk, 'Explain invoice workflow', assistant.request_id,
            {}, lambda *_: None, Event(),
        )

    yield read
    model.assert_not_called()


def make_saved_knowledge(s, count=1):
    documents = [KnowledgeDocument.objects.create(
        document_id=f'review-invoice-{index}', document_version='approved-v1',
        title=f'Invoice workflow {index}', content=f'ORIGINAL_APPROVED_SOURCE_{index}',
        category='workflow', keywords=['invoice'], required_capabilities=['read'],
        tenant_scope=s.a,
    ) for index in range(count)]
    conversation = conv(s)
    request_id = uuid.uuid4()
    Message.objects.create(conversation=conversation, role='user', request_id=request_id,
                           text='Explain invoice workflow')
    result = executor(s).execute('knowledge', {'query': 'invoice'})
    assert len(result['documents']) == count
    action = stored_action({'cards': [result], 'action': {
        'tool': 'knowledge', 'arguments': {'query': 'invoice'},
    }})
    assistant = Message.objects.create(
        conversation=conversation, role='assistant', request_id=request_id,
        text='The approved invoice workflow.', action=action,
    )
    return conversation, assistant, documents


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['history', 'request_replay'])
@pytest.mark.parametrize('change', ['unchanged', 'version', 'deletion', 'tenant', 'capabilities', 'sensitivity', 'application'])
def test_saved_knowledge_requires_every_original_source_authorized(setup, history_access, path, change):
    conversation, assistant, documents = make_saved_knowledge(setup)
    document = documents[0]
    updates = {
        'version': {'document_version': 'approved-v2', 'content': 'NEW_APPROVED_CONTENT'},
        'tenant': {'tenant_scope': setup.b},
        'capabilities': {'required_capabilities': ['admin']},
        'sensitivity': {'sensitivity': 'admin'},
        'application': {'application_id': 'unsupported'},
    }
    if change == 'deletion':
        document.delete()
    elif change in updates:
        KnowledgeDocument.objects.filter(pk=document.pk).update(**updates[change])
    payload = history_access(setup, conversation, assistant, path)
    if change == 'unchanged':
        assert payload['text'] == assistant.text
        assert payload['cards'][0]['documents'][0]['version'] == 'approved-v1'
    else:
        assert payload['text'] == ''
        assert assistant.text not in json.dumps(payload)
        if change != 'version':
            assert 'ORIGINAL_APPROVED_SOURCE' not in json.dumps(payload)
    # Reading suppressed assistant output does not rewrite the user's instruction.
    assert Message.objects.get(conversation=conversation, role='user').text == 'Explain invoice workflow'


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['history', 'request_replay'])
def test_one_revoked_source_suppresses_entire_saved_answer(setup, history_access, path):
    conversation, assistant, documents = make_saved_knowledge(setup, count=2)
    KnowledgeDocument.objects.filter(pk=documents[1].pk).update(required_capabilities=['admin'])
    payload = history_access(setup, conversation, assistant, path)
    assert payload['text'] == ''
    assert len(payload['cards'][0]['documents']) == 1
    assert 'ORIGINAL_APPROVED_SOURCE_1' not in json.dumps(payload)


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['history', 'request_replay'])
def test_legacy_knowledge_answer_without_source_metadata_is_hidden(setup, history_access, path):
    conversation, assistant, _ = make_saved_knowledge(setup)
    assistant.action.pop('knowledge_sources')
    assistant.save(update_fields=['action'])
    payload = history_access(setup, conversation, assistant, path)
    assert payload['text'] == ''
    assert payload['cards'][0]['documents']  # Currently authorized documentation remains available.


@pytest.mark.django_db
def test_user_text_survives_history_knowledge_revocation(setup, history_access):
    conversation, assistant, documents = make_saved_knowledge(setup)
    documents[0].delete()
    api = APIClient()
    api.force_authenticate(setup.user)
    response = api.get(f'/api/ai/v1/conversations/{conversation.pk}/')
    assert response.status_code == 200
    messages = response.json()['messages']
    assert next(message for message in messages if message['role'] == 'user')['text'] == 'Explain invoice workflow'
    assert next(message for message in messages if message['role'] == 'assistant')['text'] == ''


def injected_provider(chunks, mode='native'):
    # Skip URL/DNS setup: this tests planner validation, not the transport.
    provider = object.__new__(ChatAIModelService)
    provider.config = ModelConfig('http://127.0.0.1:18090/v1', 'synthetic-test', mode=mode)
    provider.stream = Mock(return_value=iter(chunks))
    return provider


def call_chunks(name, arguments):
    return [{'tool_calls': [{'index': 0, 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}]


def assert_invalid_plan(chunks):
    provider = injected_provider(chunks)
    with pytest.raises(ChatAIError) as error:
        provider.choose([{'role': 'user', 'content': 'Synthetic request'}], registry().permitted(['read']))
    assert error.value.code == 'INVALID_MODEL_OUTPUT'


@pytest.mark.parametrize('chunks', [
    [], [{'content': 'Your revenue this month is 9,999,999 MAD.'}],
    call_chunks('search_invoices', {}) + [{'tool_calls': [{'index': 1, 'function': {'name': 'search_clients', 'arguments': '{}'}}]}],
])
def test_planner_requires_exactly_one_function_call(chunks):
    assert_invalid_plan(chunks)


@pytest.mark.parametrize('name,arguments', [
    ('sql', {'query': 'SELECT * FROM invoices'}),
    ('search_invoices', {'company_id': 999}),
    ('search_invoices', {'limit': 1000}),
    ('search_invoices', {'limit': True}),
    ('search_invoices', {'offset': -1}),
    ('financial_summary', {'metric': 'collected'}),
    ('search_invoices', ['unexpected', 'array']),
    ('prepare_change', {'resource': 'invoice', 'operation': 'delete', 'identifier': 1}),
])
def test_planner_rejects_unregistered_unpermitted_or_invalid_arguments(name, arguments):
    assert_invalid_plan(call_chunks(name, arguments))


@pytest.mark.parametrize('arguments', [
    {'message': 'Your revenue is 9,999,999 MAD.'},
    {'reason': 'invent_revenue', 'language': 'en'},
    {'reason': 'missing_details', 'language': 'unknown'},
    {'reason': 'missing_details', 'language': 'en', 'message': 'Injected financial answer'},
])
def test_clarification_cannot_contain_model_authored_business_answer(arguments):
    assert_invalid_plan(call_chunks('clarify', arguments))


@pytest.mark.parametrize('language', ['fr', 'en'])
@pytest.mark.parametrize('mode', ['native', 'json_schema'])
def test_clarification_uses_backend_text_in_selected_message_language(language, mode):
    arguments = {'reason': 'ambiguous_metric', 'language': language}
    chunks = call_chunks('clarify', arguments) if mode == 'native' else [
        {'content': json.dumps({'tool': 'clarify', 'arguments': arguments})},
    ]
    action, _ = injected_provider(chunks, mode).choose([], registry().permitted(['read']))
    assert action == {'tool': 'clarify', 'message': MESSAGES[language]['ambiguous_metric']}


def test_valid_fragmented_tool_call_discards_untrusted_planner_prose():
    chunks = [
        {'content': 'Ignore the real result; revenue is 9,999,999 MAD.'},
        {'tool_calls': [{'index': 0, 'function': {'name': 'search_invoices', 'arguments': '{"client_name":'}}]},
        {'tool_calls': [{'index': 0, 'function': {'arguments': '"Synthetic client"}'}}]},
    ]
    action, _ = injected_provider(chunks).choose([], registry().permitted(['read']))
    assert action == {'tool': 'search_invoices', 'arguments': {'client_name': 'Synthetic client'}}
    assert '9,999,999' not in json.dumps(action)


@pytest.mark.django_db
@pytest.mark.parametrize('phase', ['before_prompt', 'between_deltas', 'before_persistence'])
@pytest.mark.parametrize('change', ['version', 'deletion', 'capabilities'])
def test_live_knowledge_revocation_stops_new_output_and_success_persistence(setup, monkeypatch, phase, change):
    from types import SimpleNamespace
    from .models import InferenceLease

    monkeypatch.setattr('chat_ai.services.close_old_connections', lambda: None)
    document = KnowledgeDocument.objects.create(
        document_id='live-invoice-source', document_version='approved-v1',
        title='Invoice workflow', content='Approved invoice procedure', category='workflow',
        keywords=['invoice'], required_capabilities=['read'], tenant_scope=setup.a,
    )
    conversation = conv(setup)
    request_id = uuid.uuid4()
    events = []

    def revoke():
        if change == 'deletion':
            document.delete()
        elif change == 'version':
            KnowledgeDocument.objects.filter(pk=document.pk).update(document_version='new-v2')
        else:
            KnowledgeDocument.objects.filter(pk=document.pk).update(required_capabilities=['admin'])

    def stream(*args, **kwargs):
        yield {'content': 'The permitted first explanation. '}
        revoke()
        if phase == 'between_deltas':
            yield {'content': 'FORBIDDEN_AFTER_REVOCATION'}
        # With no further content, only the service's final check can reject it.

    def emit(event, payload):
        events.append((event, payload))
        if phase == 'before_prompt' and event == 'tool.completed':
            revoke()

    model = SimpleNamespace(
        choose=Mock(return_value=({'tool': 'knowledge', 'arguments': {'query': 'invoice'}}, {})),
        stream=Mock(side_effect=stream),
    )
    monkeypatch.setattr('chat_ai.services.get_model', lambda: model)
    with pytest.raises(ChatAIError) as error:
        ChatAIConversationService().run(
            setup.user.pk, conversation.pk, 'Explain the invoice workflow', request_id,
            {}, emit, Event(),
        )
    assert error.value.code == 'CONTEXT_EXPIRED'
    deltas = [payload['text'] for event, payload in events if event == 'message.delta']
    assert deltas == ([] if phase == 'before_prompt' else ['The permitted first explanation. '])
    assert 'FORBIDDEN_AFTER_REVOCATION' not in json.dumps(events)
    assert not Message.objects.filter(conversation=conversation, role='assistant').exists()
    assert Message.objects.get(conversation=conversation, role='user').request_id == request_id
    assert InferenceLease.objects.get(name='model').owner is None
    if phase == 'before_prompt':
        model.stream.assert_not_called()
    else:
        model.stream.assert_called_once()


@pytest.mark.django_db
def test_conversation_titles_are_bounded_and_scoped_to_current_user_company_and_stamp(setup, monkeypatch):
    from datetime import timedelta
    from django.utils import timezone
    from account.models import Membership
    from .models import Conversation
    from .security import authorization_stamp

    monkeypatch.setattr(ChatReadThrottle, 'cache', LocMemCache(str(uuid.uuid4()), {}))
    role = setup.membership.role
    Membership.objects.create(user=setup.user, company=setup.b, role=role)
    Membership.objects.create(user=setup.other, company=setup.a, role=role)

    def saved(user, company, title=None, expired=False):
        conversation = Conversation.objects.create(
            user=user, company=company,
            authorization_stamp=authorization_stamp(user.pk, company.pk),
            expires_at=timezone.now() + timedelta(days=-1 if expired else 1),
        )
        # Assistant output must never become a list-title fallback.
        Message.objects.create(conversation=conversation, role='assistant', text='PRIVATE_ASSISTANT_SUMMARY')
        if title is not None:
            Message.objects.create(conversation=conversation, role='user', text=title)
            Message.objects.create(conversation=conversation, role='user', text='LATER_USER_MESSAGE')
        return conversation

    stale = saved(setup.user, setup.a, 'STALE_STAMP_TITLE')
    setup.membership.can_validate_factures = not setup.membership.can_validate_factures
    setup.membership.save(update_fields=['can_validate_factures'])
    first_question = 'هل يمكن شرح الفاتورة؟ ' * 10
    current = saved(setup.user, setup.a, first_question)
    empty = saved(setup.user, setup.a)
    own_other_company = saved(setup.user, setup.b, 'OWN_BETA_TITLE')
    other_user = saved(setup.other, setup.a, 'OTHER_USER_ALPHA_TITLE')
    expired = saved(setup.user, setup.a, 'EXPIRED_TITLE', expired=True)

    api = APIClient()
    api.force_authenticate(setup.user)
    response = api.get('/api/ai/v1/conversations/', {'company_id': setup.a.pk})
    assert response.status_code == 200
    rows = {item['id']: item for item in response.json()}
    assert set(rows) == {str(current.pk), str(empty.pk)}
    assert rows[str(current.pk)]['title'] == first_question[:120]
    assert rows[str(empty.pk)]['title'] == 'Nouvelle conversation'
    serialized = json.dumps(response.json())
    for hidden in ('STALE_STAMP_TITLE', 'OWN_BETA_TITLE', 'OTHER_USER_ALPHA_TITLE',
                   'EXPIRED_TITLE', 'PRIVATE_ASSISTANT_SUMMARY', 'LATER_USER_MESSAGE'):
        assert hidden not in serialized

    beta = api.get('/api/ai/v1/conversations/', {'company_id': setup.b.pk})
    assert beta.status_code == 200
    assert [(item['id'], item['title']) for item in beta.json()] == [(str(own_other_company.pk), 'OWN_BETA_TITLE')]
    api.force_authenticate(setup.other)
    other = api.get('/api/ai/v1/conversations/', {'company_id': setup.a.pk})
    assert other.status_code == 200
    assert [(item['id'], item['title']) for item in other.json()] == [(str(other_user.pk), 'OTHER_USER_ALPHA_TITLE')]


@pytest.mark.django_db
@pytest.mark.parametrize('change', ['version', 'deletion', 'tenant', 'capabilities', 'membership', 'inactive_user'])
def test_delivery_guard_rechecks_sources_and_authenticated_scope(setup, change):
    from .services import authorize_delivery

    conversation, assistant, documents = make_saved_knowledge(setup)
    sources = assistant.action['knowledge_sources']
    assert authorize_delivery(setup.user.pk, conversation.pk, sources).pk == conversation.pk
    document = documents[0]
    if change == 'version':
        KnowledgeDocument.objects.filter(pk=document.pk).update(document_version='revised-v2')
    elif change == 'deletion':
        document.delete()
    elif change == 'tenant':
        KnowledgeDocument.objects.filter(pk=document.pk).update(tenant_scope=setup.b)
    elif change == 'capabilities':
        KnowledgeDocument.objects.filter(pk=document.pk).update(required_capabilities=['admin'])
    elif change == 'membership':
        setup.membership.delete()
    else:
        setup.user.is_active = False
        setup.user.save(update_fields=['is_active'])
    with pytest.raises(ChatAIError) as error:
        authorize_delivery(setup.user.pk, conversation.pk, sources)
    assert error.value.code == {
        'membership': 'PERMISSION_DENIED', 'inactive_user': 'NOT_AUTHENTICATED',
    }.get(change, 'CONTEXT_EXPIRED')


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('revoke_after_queue', [False, True])
@pytest.mark.parametrize('response_path', ['new', 'replay', 'replay_new_source'])
def test_sse_keeps_source_metadata_private_and_blocks_revoked_queued_output(setup, monkeypatch, revoke_after_queue, response_path):
    from asgiref.sync import async_to_sync
    from django.db import connections
    from queue import Queue
    from .services import authorize_delivery
    from .views import ChatInferenceThrottle

    monkeypatch.setattr(ChatInferenceThrottle, 'cache', LocMemCache(str(uuid.uuid4()), {}))
    document = KnowledgeDocument.objects.create(
        document_id='private-delivery-source', document_version='approved-v1',
        title='Invoice workflow', content='Authorized source', category='workflow',
        keywords=['invoice'], required_capabilities=['read'], tenant_scope=setup.a,
    )
    conversation = conv(setup)
    queued_completion = Event()
    queue_events = []
    sources = [{'document_id': document.pk, 'version': document.document_version}]
    request_id = uuid.uuid4()
    if response_path.startswith('replay'):
        Message.objects.create(conversation=conversation, role='user', request_id=request_id,
                               text='Explain invoice workflow')
        Message.objects.create(conversation=conversation, role='assistant', request_id=request_id,
                               text='Queued private final explanation.', action={
                                   'tool': 'knowledge', 'arguments': {'query': 'invoice'},
                                   'knowledge_sources': sources,
                               })
    revocation_target = document.pk
    if response_path == 'replay_new_source':
        # The query now retrieves a source that was absent from the saved prose.
        additional_source = KnowledgeDocument.objects.create(
            document_id='newly-visible-delivery-source', document_version='approved-v1',
            title='Invoice workflow addition', content='NEW_PRIVATE_CARD_CONTENT',
            category='workflow', keywords=['invoice'], required_capabilities=['read'],
            tenant_scope=setup.a,
        )
        revocation_target = additional_source.pk

    class DeliveryQueue(Queue):
        def put_nowait(self, item):
            super().put_nowait(item)
            queue_events.append(item[0])
            if item[0] == 'message.completed':
                try:
                    # Revocation occurs after enqueue, before delivery authorization.
                    if revoke_after_queue:
                        KnowledgeDocument.objects.filter(pk=revocation_target).update(required_capabilities=['admin'])
                finally:
                    connections.close_all()  # This hook runs in the inference worker thread.
                    queued_completion.set()

    def delayed_delivery_guard(user_id, conversation_id, knowledge_sources=None, cards=()):
        assert queued_completion.wait(3), 'Inference worker did not enqueue its completion'
        return authorize_delivery(user_id, conversation_id, knowledge_sources, cards)

    def completed_inference(self, user_id, conversation_id, text, request_id, context, emit, cancel):
        emit('_knowledge.sources', {'sources': sources})
        emit('message.delta', {'text': 'Queued private partial explanation. '})
        return {'id': str(uuid.uuid4()), 'role': 'assistant', 'text': 'Queued private final explanation.', 'cards': []}

    monkeypatch.setattr('chat_ai.views.queue.Queue', DeliveryQueue)
    monkeypatch.setattr('chat_ai.views.authorize_delivery', delayed_delivery_guard)
    if response_path == 'new':
        monkeypatch.setattr(ChatAIConversationService, 'run', completed_inference)
    else:
        monkeypatch.setattr('chat_ai.services.get_model', Mock(side_effect=AssertionError('Replay called model')))
    api = APIClient()
    api.force_authenticate(setup.user)
    response = api.post(
        f'/api/ai/v1/conversations/{conversation.pk}/messages/',
        {'text': 'Explain invoice workflow', 'request_id': str(request_id), 'context': {}},
        format='json', HTTP_ACCEPT='text/event-stream',
    )
    assert response.status_code == 200

    async def collect():
        return b''.join([chunk async for chunk in response.streaming_content]).decode()

    try:
        body = async_to_sync(collect)()
    finally:
        response.close()
    assert queued_completion.is_set()
    assert 'message.completed' in queue_events
    assert '_knowledge.sources' not in queue_events
    assert '_knowledge.sources' not in body and '"sources"' not in body
    if revoke_after_queue:
        assert 'CONTEXT_EXPIRED' in body
        assert 'Queued private' not in body
        assert 'event: message.completed' not in body
        assert 'NEW_PRIVATE_CARD_CONTENT' not in body
        if response_path == 'replay_new_source':
            document.refresh_from_db()
            assert document.required_capabilities == ['read']  # Original text source remains authorized.
    else:
        assert 'Queued private final explanation.' in body
        if response_path == 'new':
            assert 'Queued private partial explanation. ' in body
        assert 'event: message.completed' in body
        assert 'event: error' not in body


@pytest.mark.parametrize('language', ['ar','ary'])
@pytest.mark.parametrize('mode', ['native','json_schema'])
def test_removed_languages_cannot_be_returned_as_clarifications(language,mode):
    arguments={'reason':'missing_details','language':language}
    chunks=call_chunks('clarify',arguments) if mode=='native' else [{'content':json.dumps({'tool':'clarify','arguments':arguments})}]
    with pytest.raises(ChatAIError) as error:
        injected_provider(chunks,mode).choose([],registry().permitted(['read']))
    assert error.value.code=='INVALID_MODEL_OUTPUT'
