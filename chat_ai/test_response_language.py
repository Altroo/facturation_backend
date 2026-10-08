from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from chat_ai_assistant.orchestrator import ChatAIOrchestrator


@pytest.mark.parametrize('question,interface,language', [
    ('How do I create an invoice?', 'fr', 'English'),
    ('Comment créer une facture client ?', 'en', 'French'),
    ('Tell me about this status.', 'fr', 'English'),
    ('Où se trouve la liste des clients ?', 'en', 'French'),
])
def test_knowledge_answer_language_follows_question_not_interface(question, interface, language):
    document = {'document_id': 'test', 'version': '1', 'title': 'Facture', 'content': 'Verified workflow'}
    executor = SimpleNamespace(authorize=Mock(), capabilities=lambda: [],
                               execute=Mock(return_value={'type': 'knowledge', 'documents': [document]}),
                               authorize_knowledge=Mock(), output_labels=lambda: {})
    model = SimpleNamespace(stream=Mock(return_value=iter([{'content': 'Verified answer.'}])))
    registry = SimpleNamespace(permitted=lambda _: [])
    ChatAIOrchestrator(model, registry, executor).run(
        question, context={'interface_language': interface},
        forced_action={'tool': 'knowledge', 'arguments': {'query': question}},
    )
    prompts = model.stream.call_args.args[0]
    assert 'Answer in ' + language + '.' in prompts[0]['content']
    assert question in prompts[1]['content']
    executor.authorize_knowledge.assert_called_with([document])


@pytest.mark.parametrize('question,interface,expected', [
    ('How do I create an invoice?', 'fr', '1. Click “New client invoice”.\n2. Click “Add items”.'),
    ('Comment créer une facture client ?', 'en', '1. Cliquez sur « Nouvelle facture client ».\n2. Cliquez sur « Ajouter des articles ».'),
])
def test_verified_workflow_keeps_native_captions_and_current_language(question, interface, expected):
    document = {'document_id': 'invoice-create', 'version': '1', 'title': 'Créer une facture',
                'content': 'Legacy description', 'localized_content': {
                    'en': '1. Click “New client invoice”.\n2. Click “Add items”.',
                    'fr': '1. Cliquez sur « Nouvelle facture client ».\n2. Cliquez sur « Ajouter des articles ».',
                }}
    executor = SimpleNamespace(authorize=Mock(), capabilities=lambda: [],
                               execute=Mock(return_value={'type': 'knowledge', 'documents': [document]}),
                               authorize_knowledge=Mock(), output_labels=lambda: {})
    model = SimpleNamespace(stream=Mock(side_effect=AssertionError('Do not rewrite verified procedures')))
    events = []
    result = ChatAIOrchestrator(model, SimpleNamespace(permitted=lambda _: []), executor).run(
        question, context={'interface_language': interface},
        forced_action={'tool': 'knowledge', 'arguments': {'query': question}},
        emit=lambda event, data: events.append((event, data)),
    )
    assert result['text'] == expected
    assert ''.join(data['text'] for event, data in events if event == 'message.delta') == expected
    model.stream.assert_not_called()
    assert executor.authorize_knowledge.call_count == 4


@pytest.mark.parametrize('stop', ['revoke', 'cancel'])
def test_verified_workflow_stops_at_revocation_or_cancellation(stop):
    from threading import Event
    from chat_ai_assistant.contracts import ChatAIError
    document = {'document_id': 'invoice-create', 'version': '1', 'localized_content': {
        'en': 'Permitted first step.\nMust not reach the user.', 'fr': 'Première étape.'}}
    executor = SimpleNamespace(authorize=Mock(), capabilities=lambda: [],
                               execute=Mock(return_value={'type': 'knowledge', 'documents': [document]}),
                               authorize_knowledge=Mock(), output_labels=lambda: {})
    cancellation = Event()
    delivered = []
    def emit(event, data):
        if event == 'message.delta':
            delivered.append(data['text'])
            if stop == 'revoke':
                executor.authorize_knowledge.side_effect = ChatAIError('CONTEXT_EXPIRED')
            else:
                cancellation.set()
    with pytest.raises(ChatAIError) as error:
        ChatAIOrchestrator(SimpleNamespace(stream=Mock()), SimpleNamespace(permitted=lambda _: []), executor).run(
            'How do I create an invoice?', context={'interface_language': 'fr'},
            forced_action={'tool': 'knowledge', 'arguments': {'query': 'create invoice'}},
            emit=emit, cancel=cancellation,
        )
    assert error.value.code == ('CONTEXT_EXPIRED' if stop == 'revoke' else 'CANCELLED')
    assert delivered == ['Permitted first step.\n']
