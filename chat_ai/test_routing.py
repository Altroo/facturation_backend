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
