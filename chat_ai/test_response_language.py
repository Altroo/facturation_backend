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
