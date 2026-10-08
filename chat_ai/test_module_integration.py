"""Integration regressions across registered tools, delivery and human-facing output."""
import json
from threading import Event
from unittest.mock import Mock
import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient

from account.models import CustomUser
from article.models import Article
from reglement.models import Reglement
from chat_ai_assistant.contracts import ChatAIError
from chat_ai_assistant.orchestrator import ChatAIOrchestrator
from chat_ai_assistant.presentation import LabelledTextStream, labelled_text
from . import services
from .labels import FIELD_LABELS
from .models import AuditEvent, KnowledgeDocument, Message
from .services import replay_message, stored_action
from .tests import setup, conv, executor, assert_code
from .test_catalog import staff, payment
from .test_operations import records
from .tools import ChatAIToolExecutor, registry
from .views import ChatInferenceThrottle, ChatReadThrottle


RESOURCE_ROUTES = [
    ('article', 'articles'), ('payment', 'reglements'), ('user', 'users'),
    ('stock_balance', 'stock'), ('stock_movement', 'stock/movements'),
    ('stock_receipt', 'stock/receipts'), ('stock_inventory', 'stock/inventories'),
    ('logistics_order', 'logistique'),
]


@pytest.mark.django_db
@pytest.mark.parametrize('resource,route', RESOURCE_ROUTES)
def test_registered_search_detail_and_navigation_execute_real_adapters(setup, staff, payment, records, resource, route):
    objects = {**records.objects, 'article': records.article, 'payment': payment, 'user': setup.other}
    obj = objects[resource]
    tool, arguments = {
        'article': ('search_articles', {'reference': records.article.reference}),
        'payment': ('search_payments', {'invoice_number': setup.invoice.numero_facture}),
        'user': ('search_users', {'email': setup.other.email}),
    }.get(resource, ('search_operations', {'resource': resource}))
    ex = executor(setup)
    searched = ex.execute(tool, arguments)
    assert [item['id'] for item in searched['items']] == [obj.pk]
    detail = ex.execute('get_record', {'resource': resource, 'identifier': obj.pk})
    assert detail['items'][0]['id'] == obj.pk
    if resource in {'stock_receipt', 'stock_inventory', 'logistics_order'}:
        assert detail['items'][0]['lines'][0]['product_name'] == 'Synthetic item'
    target = ex.execute('navigate', {'resource': resource, 'identifier': obj.pk})['target']
    expected = f'/dashboard/{route}/{obj.pk}/'
    if resource != 'user':
        expected += f'?company_id={setup.a.pk}'
    assert target['path'] == expected
    assert ex.state['resource'] == resource and ex.state['ids'] == [obj.pk]
    assert list(AuditEvent.objects.filter(correlation_id=ex.correlation_id).values_list('tool', 'outcome')) == [
        (tool, 'allowed'), ('get_record', 'allowed'), ('navigate', 'allowed')]
    assert 'SECRET_' not in json.dumps([searched, detail, target])


@pytest.mark.django_db
def test_staff_tool_visibility_and_every_user_entry_point_recheck_native_staff(setup):
    ex = executor(setup)
    assert 'search_users' not in {tool.name for tool in registry().permitted(ex.capabilities())}
    for name, args in [
        ('search_users', {'email': setup.other.email}),
        ('get_record', {'resource': 'user', 'identifier': setup.other.pk}),
        ('navigate', {'resource': 'user', 'identifier': setup.other.pk}),
        ('navigate', {'resource': 'users'}),
    ]:
        assert_code('PERMISSION_DENIED', lambda: executor(setup).execute(name, args))
    CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=True)
    assert 'search_users' in {tool.name for tool in registry().permitted(ex.capabilities())}
    assert executor(setup).execute('search_users', {})['items'][0]['id'] == setup.other.pk
    CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=False)
    assert 'search_users' not in {tool.name for tool in registry().permitted(ex.capabilities())}
    assert_code('PERMISSION_DENIED', lambda: executor(setup).execute('search_users', {}))


@pytest.mark.django_db
@pytest.mark.parametrize('resource', ['article', 'user'])
def test_history_and_previous_navigation_do_not_reuse_revoked_references(setup, staff, resource):
    obj = Article.objects.get(company=setup.a, reference='SYNTH-ITEM') if resource == 'article' else setup.other
    ex = executor(setup)
    result = ex.execute('get_record', {'resource': resource, 'identifier': obj.pk})
    conversation = conv(setup)
    message = Message.objects.create(conversation=conversation, role='assistant', text='',
        action=stored_action({'cards': [result]}))
    if resource == 'article':
        Article.objects.filter(pk=obj.pk).update(company=setup.b)
        expected_code = 'NOT_FOUND'
    else:
        CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=False)
        expected_code = 'PERMISSION_DENIED'
    assert_code(expected_code, lambda: ex.execute('previous_results', {'operation': 'open', 'index': 1}))
    payload = replay_message(executor(setup), message)
    assert not payload['cards'] or not payload['cards'][0]['items']
    assert str(obj.pk) not in json.dumps(payload['cards'])


@pytest.mark.parametrize('args', [
    {'resource': 'stock_balance', 'client_name': 'Atlas'},
    {'resource': 'stock_inventory', 'supplier_name': 'Atlas'},
    {'resource': 'stock_movement', 'status': 'draft'},
    {'resource': 'stock_receipt', 'status': 'Validée'},
    {'resource': 'stock_balance', 'status': 'paid'},
    {'resource': 'stock_receipt', 'company_id': 123},
    {'resource': 'stock_balance', 'reference__regex': '.*'},
    {'resource': 'stock_balance', 'limit': True},
])
def test_advertised_operation_schema_rejects_unsupported_fields_and_statuses(args):
    assert_code('INVALID_ARGUMENTS', lambda: registry().validate('search_operations', args))


@pytest.mark.parametrize('args', [
    {'resource': 'stock_balance', 'status': 'minimum', 'product_name': 'Peinture'},
    {'resource': 'stock_movement', 'status': 'receipt'},
    {'resource': 'stock_receipt', 'status': 'validated', 'client_name': 'Atlas'},
    {'resource': 'stock_inventory', 'status': 'draft'},
    {'resource': 'logistics_order', 'status': 'Production', 'supplier_name': 'Atlas'},
])
def test_advertised_operation_schema_accepts_supported_searches(args):
    assert registry().validate('search_operations', args).name == 'search_operations'


@pytest.fixture
def json_api(monkeypatch):
    # Keep pytest's transaction open; the actual request, service and DB queries run.
    monkeypatch.setattr('chat_ai.services.close_old_connections', lambda: None)
    monkeypatch.setattr(ChatInferenceThrottle, 'cache', LocMemCache(str(uuid.uuid4()), {}))
    monkeypatch.setattr(ChatReadThrottle, 'cache', LocMemCache(str(uuid.uuid4()), {}))
    return APIClient()


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['fresh', 'cached', 'history'])
@pytest.mark.parametrize('revocation', ['record_company', 'membership', 'staff'])
def test_json_delivery_rechecks_access_after_result_was_built(setup, staff, json_api, monkeypatch, path, revocation):
    article = Article.objects.get(company=setup.a, reference='SYNTH-ITEM')
    Article.objects.filter(pk=article.pk).update(designation='Private article business value')
    resource, obj, tool, args = ('user', setup.other, 'search_users', {'email': setup.other.email}) if revocation == 'staff' else (
        'article', article, 'search_articles', {'reference': article.reference})
    conversation = conv(setup)
    request_id = uuid.uuid4()
    built = []

    def revoke():
        if revocation == 'record_company':
            Article.objects.filter(pk=article.pk).update(company=setup.b)
        elif revocation == 'membership':
            setup.membership.delete()
        else:
            CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=False)

    if path == 'fresh':
        model = Mock()
        model.choose.return_value = ({'tool': tool, 'arguments': args}, {})
        monkeypatch.setattr('chat_ai.services.get_model', lambda: model)
        original = ChatAIToolExecutor.execute
        def executed_then_revoked(self, name, arguments):
            result = original(self, name, arguments)
            assert result['items'][0]['id'] == obj.pk
            built.append(result)
            revoke()
            return result
        monkeypatch.setattr(ChatAIToolExecutor, 'execute', executed_then_revoked)
    else:
        Message.objects.create(conversation=conversation, role='user', request_id=request_id, text='Find the record')
        Message.objects.create(conversation=conversation, role='assistant', request_id=request_id, text='',
            action={'resource': resource, 'ids': [obj.pk]})
        original = services.replay_message
        def replayed_then_revoked(ex, message):
            result = original(ex, message)
            if message.role == 'assistant':
                assert result['cards'][0]['items'][0]['id'] == obj.pk
                built.append(result)
                revoke()
            return result
        monkeypatch.setattr('chat_ai.services.replay_message', replayed_then_revoked)
        monkeypatch.setattr('chat_ai.views.replay_message', replayed_then_revoked)
        monkeypatch.setattr('chat_ai.services.get_model', Mock(side_effect=AssertionError('Replay must not call model')))
    json_api.force_authenticate(setup.user)
    if path == 'history':
        response = json_api.get(f'/api/ai/v1/conversations/{conversation.pk}/')
    else:
        response = json_api.post(f'/api/ai/v1/conversations/{conversation.pk}/messages/',
            {'text': 'Find the record', 'request_id': str(request_id), 'context': {}}, format='json')
    assert built, 'The test must revoke access after a private result was materialized'
    assert response.status_code == (403 if revocation == 'membership' else 409)
    body = response.content.decode()
    assert 'Private article business value' not in body and setup.other.email not in body
    assert 'cards' not in body
    if path == 'fresh':
        assert not Message.objects.filter(conversation=conversation, role='assistant').exists()


TECHNICAL_LABELS = [(key, label) for key, label in FIELD_LABELS.items() if '_' in key]


@pytest.mark.parametrize('key,label', TECHNICAL_LABELS)
@pytest.mark.parametrize('wrapper', ['', '`', '**', '_'])
def test_human_field_labels_survive_every_possible_stream_split(key, label, wrapper):
    raw = f'Champ : {wrapper}{key}{wrapper}. القيمة reste 12.'
    expected = f'Champ : {wrapper}{label}{wrapper}. القيمة reste 12.'
    for split in range(len(raw) + 1):
        stream = LabelledTextStream(FIELD_LABELS)
        emitted = ''
        for chunk in (raw[:split], raw[split:]):
            emitted += stream.feed(chunk)
            assert expected.startswith(emitted), f'Leaked partial field at split {split}: {emitted!r}'
        emitted += stream.feed('', final=True)
        assert emitted == expected
        assert key not in emitted


@pytest.mark.parametrize('wrapper', ['', '`', '**', '_'])
def test_unknown_technical_keys_are_rejected_before_stream_delivery(wrapper):
    raw = f'Valeur : {wrapper}private_unregistered_field{wrapper}.'
    for split in range(len(raw) + 1):
        stream = LabelledTextStream(FIELD_LABELS)
        emitted = []
        with pytest.raises(ChatAIError) as error:
            for chunk in (raw[:split], raw[split:]):
                emitted.append(stream.feed(chunk))
            emitted.append(stream.feed('', final=True))
        assert error.value.code == 'INVALID_MODEL_OUTPUT'
        assert 'private_' not in ''.join(emitted)


@pytest.mark.django_db
@pytest.mark.parametrize('raw,expected', [
    ('Consultez `raison_sociale` puis date_echeance', 'Consultez `Raison sociale` puis Date d\'échéance'),
    ('القيمة **physical_quantity**.', 'القيمة **Physique**.'),
])
def test_real_knowledge_orchestrator_only_emits_labelled_text_and_flushes_tail(setup, raw, expected):
    KnowledgeDocument.objects.create(document_id='labelled-workflow', document_version='1',
        title='Invoice workflow', content='Approved workflow', category='workflow', keywords=['invoice'],
        required_capabilities=['read'], tenant_scope=setup.a)
    model = Mock()
    model.choose.return_value = ({'tool': 'knowledge', 'arguments': {'query': 'invoice'}}, {})
    model.stream.return_value = ({'content': char} for char in raw)
    events = []
    result = ChatAIOrchestrator(model, registry(), executor(setup)).run('Explain invoice workflow',
        context={'application': 'facturation'}, emit=lambda event, data: events.append((event, data)), cancel=Event())
    visible = ''.join(data['text'] for event, data in events if event == 'message.delta')
    assert visible == result['text'] == expected
    assert any(event == 'tool.completed' for event, _ in events)


@pytest.mark.django_db
def test_knowledge_orchestrator_rejects_unmapped_identifier_without_leaking_it(setup):
    KnowledgeDocument.objects.create(document_id='unknown-label-workflow', document_version='1',
        title='Invoice workflow', content='Approved workflow', category='workflow', keywords=['invoice'],
        required_capabilities=['read'], tenant_scope=setup.a)
    model = Mock()
    model.choose.return_value = ({'tool': 'knowledge', 'arguments': {'query': 'invoice'}}, {})
    model.stream.return_value = ({'content': char} for char in 'Champ : unknown_private_field.')
    events = []
    assert_code('INVALID_MODEL_OUTPUT', lambda: ChatAIOrchestrator(model, registry(), executor(setup)).run(
        'Explain invoice workflow', context={'application': 'facturation'},
        emit=lambda event, data: events.append((event, data)), cancel=Event()))
    assert 'unknown_' not in ''.join(data['text'] for event, data in events if event == 'message.delta')


@pytest.mark.django_db
@pytest.mark.parametrize('old_text,resource,expected', [
    ('edit · proforma sélectionné', 'proforma', 'Modifier · Facture pro forma sélectionné'),
    ('delete · credit_note sélectionné', 'credit_note', 'Supprimer · Facture d’avoir sélectionné'),
    ('Modifier · delivery_note sélectionné', 'delivery_note', 'Modifier · Bon de livraison sélectionné'),
    ('edit · account_table sélectionné', 'account_table', 'Document sélectionné'),
])
def test_old_selected_resource_messages_replay_with_existing_app_labels(setup, old_text, resource, expected):
    message = Message.objects.create(conversation=conv(setup), role='user', text=old_text,
        action={'selected_resource': resource, 'selected_identifier': 1})
    assert replay_message(executor(setup), message)['text'] == expected


@pytest.mark.django_db
@pytest.mark.parametrize('text,expected', [
    ('Voir raison_sociale et date_echeance.', "Voir Raison sociale et Date d'échéance."),
    ('Voir unknown_table_name.', ''),
])
def test_old_assistant_messages_never_replay_unlabelled_internal_keys(setup, text, expected):
    message = Message.objects.create(conversation=conv(setup), role='assistant', text=text)
    assert replay_message(executor(setup), message)['text'] == expected


@pytest.mark.django_db
def test_nonmember_superuser_has_only_native_stock_schemas_and_business_denials(setup, records):
    CustomUser.objects.filter(pk=setup.user.pk).update(is_superuser=True, is_staff=False)
    setup.membership.delete()
    ex = executor(setup)
    advertised = {tool.name: tool for tool in registry().permitted(ex.capabilities())}
    assert 'search_users' not in advertised
    assert not {'search_invoices', 'search_articles', 'search_payments', 'financial_summary'} & set(advertised)
    operation_resources = {branch['properties']['resource']['const']
                           for branch in advertised['search_operations'].input_schema['oneOf']}
    assert operation_resources == {'stock_balance', 'stock_movement', 'stock_receipt', 'stock_inventory'}
    for name in ('get_record', 'navigate'):
        resources = advertised[name].input_schema['properties']['resource']['enum']
        assert 'stock_balance' in resources
        assert not {'article', 'payment', 'user', 'users', 'invoice', 'invoices', 'logistics_order'} & set(resources)
    for name, args in [
        ('search_articles', {}), ('search_invoices', {}), ('search_quotes', {}),
        ('search_documents', {'resource': 'proforma'}), ('search_clients', {}),
        ('search_payments', {}),
        ('financial_summary', {'metric': 'collected', 'period': 'current_month', 'currency': 'MAD'}),
        ('get_record', {'resource': 'article', 'identifier': records.article.pk}),
        ('search_operations', {'resource': 'logistics_order'}), ('navigate', {'resource': 'invoices'}),
    ]:
        assert_code('PERMISSION_DENIED', lambda: executor(setup).execute(name, args))
    result = ex.execute('search_operations', {'resource': 'stock_balance'})
    assert result['items'][0]['id'] == records.balance.pk
    assert ex.execute('previous_results', {'operation': 'open', 'index': 1})['target']['identifier'] == records.balance.pk
    CustomUser.objects.filter(pk=setup.user.pk).update(is_staff=True)
    advertised_staff = {tool.name: tool for tool in registry().permitted(ex.capabilities())}
    assert 'search_users' in advertised_staff
    assert 'user' in advertised_staff['get_record'].input_schema['properties']['resource']['enum']
    assert executor(setup).execute('search_users', {})['items'][0]['id'] == setup.other.pk
    assert_code('PERMISSION_DENIED', lambda: executor(setup).read_records('article', [records.article.pk]))


@pytest.mark.django_db
def test_nonmember_superuser_reaches_stock_through_real_json_orchestrator_and_replays(setup, records, json_api, monkeypatch):
    CustomUser.objects.filter(pk=setup.user.pk).update(is_superuser=True, is_staff=False)
    setup.user.refresh_from_db()
    setup.membership.delete()
    conversation = conv(setup)
    request_id = uuid.uuid4()
    model = Mock()
    model.choose.return_value = ({'tool': 'search_operations', 'arguments': {'resource': 'stock_balance'}}, {})
    monkeypatch.setattr('chat_ai.services.get_model', lambda: model)
    json_api.force_authenticate(setup.user)
    url = f'/api/ai/v1/conversations/{conversation.pk}/messages/'
    payload = {'text': 'Montre le stock disponible', 'request_id': str(request_id), 'context': {}}
    fresh = json_api.post(url, payload, format='json')
    assert fresh.status_code == 200, fresh.content
    assert fresh.json()['cards'][0]['items'][0]['id'] == records.balance.pk
    model.choose.assert_called_once()
    cached = json_api.post(url, payload, format='json')
    assert cached.status_code == 200
    assert cached.json()['cards'][0]['items'][0]['id'] == records.balance.pk
    model.choose.assert_called_once()
    CustomUser.objects.filter(pk=setup.user.pk).update(is_superuser=False)
    denied = json_api.post(url, payload, format='json')
    assert denied.status_code == 403
    assert 'Synthetic item' not in denied.content.decode()


def test_empty_knowledge_response_uses_current_message_language():
    from chat_ai_assistant.clarifications import missing_knowledge_message
    assert missing_knowledge_message('How does this work?').startswith('I could not')
    assert missing_knowledge_message('Comment fonctionne cette page ?', 'en').startswith('Je ne trouve')
    assert missing_knowledge_message('?', 'en').startswith('I could not')
    assert missing_knowledge_message('?', 'fr').startswith('Je ne trouve')


@pytest.mark.django_db
def test_form_labels_follow_interface_language_without_manual_chat_selector(setup):
    ex=executor(setup)
    assert ex.output_labels()['termes_paiement']=='Termes de paiement'
    ex.context={'interface_language':'en'}
    assert ex.output_labels()['termes_paiement']=='Payment terms'


@pytest.mark.django_db
def test_stock_superuser_knowledge_cannot_retrieve_member_docs(setup):
    from .models import KnowledgeDocument
    from account.models import CustomUser
    setup.membership.delete()
    CustomUser.objects.filter(pk=setup.user.pk).update(is_superuser=True)
    KnowledgeDocument.objects.create(document_id='members-invoice',document_version='1',title='Invoice',content='Restricted invoice workflow',category='workflow',keywords=['invoice'],required_capabilities=['read'])
    KnowledgeDocument.objects.create(document_id='stock-only',document_version='1',title='Stock',content='Approved stock quantities',category='workflow',keywords=['stock'],required_capabilities=['stock_read'])
    ex=executor(setup)
    assert ex.execute('knowledge',{'query':'invoice'})['documents']==[]
    result=ex.execute('knowledge',{'query':'stock'})
    assert [d['document_id'] for d in result['documents']]==['stock-only']
    ex.authorize_knowledge(result['documents'])
    assert_code('CONTEXT_EXPIRED',lambda:ex.authorize_knowledge([{'document_id':'members-invoice','version':'1'}]))


@pytest.mark.parametrize('key,label', [('prenom','Prénom'),('dateEcheance','Date d\'échéance'),('raisonSociale','Raison sociale')])
def test_plain_and_camel_case_field_labels_are_never_streamed_raw(key,label):
    raw=f'Champ `{key}`.'
    for split in range(len(raw)+1):
        stream=LabelledTextStream(FIELD_LABELS)
        result=stream.feed(raw[:split])+stream.feed(raw[split:])+stream.feed('',final=True)
        assert result==f'Champ `{label}`.'


@pytest.mark.parametrize('command_text,field,value', [
    ('Termes de paiement 30 jours','termes_paiement','30 jours'),
    ('Payment terms: 30 days','termes_paiement','30 days'),
    ('Date d’échéance 2026-11-08','date_echeance','2026-11-08'),
    ("Date d'échéance: 2026-11-08",'date_echeance','2026-11-08'),
    ('Due date 2026-11-08','date_echeance','2026-11-08'),
    ('Remarque: Nouvelle note','remarque','Nouvelle note'),
])
def test_edit_shortcut_accepts_visible_form_labels(command_text,field,value):
    from .shortcuts import shortcut_action
    assert shortcut_action('/modifier 0901/26 '+command_text)=={
        'tool':'prepare_change','arguments':{'resource':'invoice','invoice_number':'0901/26',
        'operation':'update','changes':{field:value}}}


def test_edit_shortcut_never_treats_unknown_field_prose_as_invoice_number():
    from .shortcuts import shortcut_action
    assert shortcut_action('/modifier 0901/26 mets une note de livraison') is None
    assert shortcut_action('/modifier 0901/26')['arguments']['invoice_number']=='0901/26'


def test_visible_reference_and_ordinary_french_words_are_preserved():
    text='Cherchez le nom du client Atlas_2026 à cette adresse.'
    for split in range(len(text)+1):
        stream=LabelledTextStream(FIELD_LABELS)
        assert stream.feed(text[:split])+stream.feed(text[split:])+stream.feed('',final=True)==text


@pytest.mark.django_db
def test_company_specific_article_labels_and_values_follow_existing_form(setup):
    from . import catalog
    item=Article.objects.get(company=setup.a,reference='SYNTH-ITEM')
    ex=executor(setup)
    assert ex.output_labels()['prix_vente']=='Prix de vente'
    assert 'purchase_amount' in catalog.card('article',item,setup.a.pk)
    setup.a.raison_sociale='IMMOBILIERE NECTAR'
    setup.a.save(update_fields=['raison_sociale'])
    assert ex.output_labels()['prix_vente']=='Prix H.T.'
    ex.context={'interface_language':'en'}
    assert ex.output_labels()['prix_vente']=='Price excl. tax'
    result=catalog.card('article',item,setup.a.pk)
    assert result['sale_label']=='price_excl_tax'
    assert 'purchase_amount' not in result and 'purchase_currency' not in result


@pytest.mark.django_db
def test_history_title_uses_labels_without_rewriting_user_instruction(setup):
    conversation=conv(setup)
    original='/modifier 0901/26 termes_paiement 30 jours'
    msg=Message.objects.create(conversation=conversation,role='user',text=original)
    api=APIClient();api.force_authenticate(setup.user)
    response=api.get('/api/ai/v1/conversations/',{'company_id':setup.a.pk})
    item=next(item for item in response.json() if item['id']==str(conversation.pk))
    assert item['title']=='/modifier 0901/26 Termes de paiement 30 jours'
    msg.refresh_from_db();assert msg.text==original


@pytest.mark.django_db
def test_capabilities_advertise_only_english_and_french(setup):
    api=APIClient();api.force_authenticate(setup.user)
    assert api.get('/api/ai/v1/capabilities/').json()['languages']==['fr','en']


@pytest.mark.parametrize('text,interface,expected',[
    ('Tell me about creating an invoice','fr','I could not'),
    ('Où se trouve le champ Date d’échéance ?','en','Je ne trouve'),
    ('How do I edit Raison sociale?','fr','I could not'),
    ('Explique le champ Payment terms','en','Je ne trouve'),
])
def test_fallback_tracks_current_message_in_both_supported_languages(text,interface,expected):
    from chat_ai_assistant.clarifications import missing_knowledge_message
    assert missing_knowledge_message(text,interface).startswith(expected)


@pytest.mark.django_db
def test_service_preserves_validated_interface_language_for_empty_knowledge(setup,monkeypatch):
    monkeypatch.setattr(services,'close_old_connections',lambda:None)
    model=Mock();model.choose.return_value=({'tool':'knowledge','arguments':{'query':'zz-no-approved-match-zz'}},{})
    monkeypatch.setattr(services,'get_model',lambda:model)
    conversation=conv(setup)
    result=services.ChatAIConversationService().run(setup.user.pk,conversation.pk,'?',uuid.uuid4(),{'interface_language':'en'},lambda *_:None,Event())
    assert result['text'].startswith('I could not')
    assert '"interface_language": "en"' in model.choose.call_args.args[0][0]['content']
