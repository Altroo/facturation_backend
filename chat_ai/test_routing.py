"""DB-free regressions for natural action nouns and production capability filtering."""
import pytest

from chat_ai_assistant.routing import shortlist
from .tools import registry


@pytest.mark.parametrize('text', [
    'I need a preview for deletion of this customer.',
    'Je souhaite une confirmation pour la suppression de ce client.',
])
def test_natural_deletion_nouns_offer_only_registered_proposal(text):
    permitted = registry().permitted(['context', 'stock_read', 'read', 'create', 'mutate'])
    offered = shortlist(text, permitted)
    names = {tool.name for tool in offered}
    assert 'prepare_change' in names
    assert names <= {tool.name for tool in permitted}


@pytest.mark.parametrize('text', [
    'I need a preview for deletion of this customer.',
    'Je souhaite une confirmation pour la suppression de ce client.',
])
@pytest.mark.parametrize('capabilities', [
    ['context', 'stock_read', 'read'],
    ['context', 'stock_read'],
])
def test_action_nouns_cannot_add_unpermitted_tools(text, capabilities):
    permitted = registry().permitted(capabilities)
    names = {tool.name for tool in shortlist(text, permitted)}
    assert 'prepare_change' not in names
    assert names <= {tool.name for tool in permitted}
    if 'read' not in capabilities:
        assert 'search_clients' not in names
        assert 'financial_summary' not in names


@pytest.mark.parametrize('text', [
    'Trouve les factures du client Demo Alpha.',
    'Trouve les factures du client Denis.',
    'Find invoices for customer Officina.',
    'Find invoices for customer Ofelia.',
])
def test_customer_name_prefix_is_not_a_related_customer_request(text):
    permitted = registry().permitted(['context', 'stock_read', 'read'])
    names = {tool.name for tool in shortlist(text, permitted)}
    assert 'search_invoices' in names
    assert 'search_clients' not in names


@pytest.mark.parametrize('text', [
    'Montre le client de cette facture.',
    'Show the customer of this invoice.',
])
def test_actual_related_customer_question_keeps_customer_tool(text):
    permitted = registry().permitted(['context', 'stock_read', 'read'])
    assert 'search_clients' in {tool.name for tool in shortlist(text, permitted)}


@pytest.mark.parametrize('text', ['Show unpaid customer invoices.', 'Help me find something.'])
@pytest.mark.parametrize('context', [None, {}, {'previous_result_type': 'invoice', 'previous_result_count': 0}])
def test_new_search_does_not_offer_a_followup_without_results(text, context):
    permitted = registry().permitted(['context', 'stock_read', 'read'])
    offered = {tool.name for tool in shortlist(text, permitted, context)}
    assert 'previous_results' not in offered
    assert 'search_invoices' in offered
    assert offered <= {tool.name for tool in permitted}


def test_existing_nonempty_results_keep_followup_available():
    permitted = registry().permitted(['context', 'stock_read', 'read'])
    offered = {tool.name for tool in shortlist(
        'Which ones are unpaid?', permitted,
        {'previous_result_type': 'invoice', 'previous_result_count': 2},
    )}
    assert 'previous_results' in offered
    assert 'search_invoices' in offered
