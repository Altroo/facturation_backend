"""Positional follow-ups use scoped state without trusting model-made IDs."""
from datetime import timedelta
from threading import Event
from unittest.mock import Mock
import uuid

import pytest
from django.utils import timezone

from chat_ai_assistant.contracts import ChatAIError
from .models import Message
from .services import ChatAIConversationService
from .shortcuts import reference_action
from .tests import setup, conv


@pytest.mark.parametrize('text,index', [
    ('Open the first result.', 1), ('Please open the second one!', 2),
    ('Open result 3', 3), ('Open the 10th result please', 10),
    ('Ouvre le deuxième résultat.', 2), ('Ouvrez la première', 1),
    ('Ouvre le résultat 3 svp', 3), ('Ouvre le dixième résultat', 10),
])
def test_exact_position_resolves_without_inventing_ids(text, index):
    assert reference_action(text, {'resource': 'invoice', 'ids': [100, 900]}) == {
        'tool': 'previous_results', 'arguments': {'operation': 'open', 'index': index}}


@pytest.mark.parametrize('text', [
    'Do not open the first result', 'Never open the first result',
    'Open the first result from another company', 'Open the first result and delete it',
    'Open the first invoice', 'Open the first result with unpaid balance',
    'Ne pas ouvrir le premier résultat', 'N’ouvre pas le premier résultat',
    'Ouvre le premier résultat puis supprime-le', 'Ouvre la deuxième facture',
    'Open result 0', 'Open result 11', 'Open result -1', 'Open result 1.5',
])
def test_extra_constraints_negation_and_resource_names_are_not_discarded(text):
    assert reference_action(text, {'resource': 'client', 'ids': [100]}) is None


def test_missing_references_and_noninvoice_unpaid_are_not_inferred():
    assert reference_action('Open the first result', {}) is None
    assert reference_action('Which ones are unpaid?', {'resource': 'quote', 'ids': [100]}) is None
    assert reference_action('Which ones are unpaid?', {'resource': 'invoice', 'ids': [100]}) == {
        'tool': 'previous_results', 'arguments': {'operation': 'unpaid'}}


@pytest.mark.django_db
@pytest.mark.parametrize('case', ['valid', 'foreign', 'expired', 'permission_revoked', 'out_of_range'])
def test_positional_service_revalidates_state_and_target_without_model(setup, monkeypatch, case):
    monkeypatch.setattr('chat_ai.services.close_old_connections', lambda: None)
    model = Mock(side_effect=AssertionError('Exact reference must not call the model'))
    monkeypatch.setattr('chat_ai.services.get_model', model)
    conversation = conv(setup)
    identifier = setup.restricted.pk if case == 'foreign' else setup.invoice.pk
    conversation.references = {
        'resource': 'invoice', 'ids': [identifier],
        'expires_at': (timezone.now() + timedelta(minutes=-1 if case == 'expired' else 10)).isoformat(),
    }
    conversation.save()
    if case == 'permission_revoked':
        setup.membership.delete()
    text = 'Open the second result' if case == 'out_of_range' else 'Open the first result'
    def run():
        return ChatAIConversationService().run(setup.user.pk, conversation.pk, text, uuid.uuid4(), {}, lambda *_: None, Event())
    if case == 'valid':
        result = run()
        assert result['cards'][0]['target']['identifier'] == setup.invoice.pk
        assert result['cards'][0]['target']['company_id'] == setup.a.pk
    else:
        with pytest.raises(ChatAIError) as error:
            run()
        assert error.value.code == {
            'foreign': 'NOT_FOUND', 'expired': 'CONTEXT_EXPIRED',
            'permission_revoked': 'PERMISSION_DENIED', 'out_of_range': 'INVALID_ARGUMENTS',
        }[case]
        assert not Message.objects.filter(conversation=conversation, role='assistant').exists()
    model.assert_not_called()


@pytest.mark.parametrize('question', [
    'How do I create a customer invoice?', 'How to find an old invoice?',
    'Comment créer une facture client ?', 'Comment valider une facture ?',
    'Explique les statuts des factures.', 'Expliquez le statut de paiement.',
    'Explain the invoice statuses.', 'What does Paid mean?', 'Que signifie TTC ?',
])
def test_explicit_general_help_routes_to_permission_filtered_knowledge(question):
    from .shortcuts import knowledge_action
    assert knowledge_action(question) == {'tool': 'knowledge', 'arguments': {'query': question}}


@pytest.mark.parametrize('question', [
    'Show unpaid invoices', 'How much money did we collect this month?',
    'Quels encaissements avons-nous reçus ce mois-ci ?', 'Explain invoice 0901/26',
    'Do not explain invoice statuses', 'Explique les statuts puis supprime la facture',
    'Find a quote with product Peinture', 'Delete the first result',
    "Explain this invoice's status", 'Explique le statut de cette facture',
    'Explain invoice statuses and show unpaid invoices', 'Explique les statuts et ouvre la première facture',
    "Explain Ahmed's invoice status", 'Explique le statut de la facture Ahmed',
])
def test_business_queries_and_specific_records_remain_with_the_planner(question):
    from .shortcuts import knowledge_action
    assert knowledge_action(question) is None


@pytest.mark.django_db
def test_general_help_uses_authorized_sources_without_model_planning(setup, monkeypatch):
    from .models import KnowledgeDocument
    monkeypatch.setattr('chat_ai.services.close_old_connections', lambda: None)
    model = Mock(side_effect=AssertionError('Approved help needs no model planning'))
    monkeypatch.setattr('chat_ai.services.get_model', model)
    KnowledgeDocument.objects.create(document_id='status-permitted', document_version='v1',
        title='Invoice status', content='Status definitions', keywords=['status','statuts','factures'],
        category='workflow', required_capabilities=['read'], tenant_scope=setup.a,
        localized_content={'fr':'Définition autorisée.', 'en':'Authorized definition.'})
    KnowledgeDocument.objects.create(document_id='status-restricted', document_version='v1',
        title='Invoice status', content='SECRET COMPANY PROCEDURE', keywords=['status','statuts','factures'],
        category='workflow', required_capabilities=['read'], tenant_scope=setup.b,
        localized_content={'fr':'SECRET COMPANY PROCEDURE', 'en':'SECRET COMPANY PROCEDURE'})
    conversation = conv(setup)
    result = ChatAIConversationService().run(setup.user.pk, conversation.pk,
        'Explique les statuts des factures.', uuid.uuid4(), {}, lambda *_: None, Event())
    assert result['text'] == 'Définition autorisée.'
    assert [d['document_id'] for d in result['cards'][0]['documents']] == ['status-permitted']
    model.assert_not_called()
