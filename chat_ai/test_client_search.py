"""Natural customer-name search retains company scope and all search terms."""
import pytest
from client.models import Client
from chat_ai_assistant.contracts import ChatAIError
from .tests import setup, executor

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('query', [
    'SYN-Lina SYN-Morel',
    'SYN-Morel SYN-Lina',
    '  SYN-Lina   SYN-Morel  ',
])
def test_customer_full_name_matches_across_fields_and_stays_scoped(setup, query):
    person = Client.objects.create(company=setup.a, client_type='PP', code_client='PERSON',
        prenom='SYN-Lina', nom='SYN-Morel')
    Client.objects.create(company=setup.a, client_type='PP', code_client='FIRST-ONLY',
        prenom='SYN-Lina', nom='Different')
    Client.objects.create(company=setup.a, client_type='PP', code_client='LAST-ONLY',
        prenom='Different', nom='SYN-Morel')
    Client.objects.create(company=setup.b, client_type='PP', code_client='FOREIGN-PERSON',
        prenom='SYN-Lina', nom='SYN-Morel')
    ex = executor(setup)
    result = ex.execute('search_clients', {'query': query})
    assert [item['id'] for item in result['items']] == [person.pk]
    assert ex.state['ids'] == [person.pk]
    assert result['items'][0]['navigation']['company_id'] == setup.a.pk


@pytest.mark.parametrize('query', ['Client Démo', 'SYNTH-A'])
def test_customer_company_name_and_code_search_remain_supported(setup, query):
    result = executor(setup).execute('search_clients', {'query': query})
    assert [item['id'] for item in result['items']] == [setup.client.pk]


def test_customer_name_search_does_not_match_unrelated_contact_fields(setup):
    Client.objects.create(company=setup.a, client_type='PM', code_client='CONTACT-ONLY',
        raison_sociale='Different', adresse='SYN-Lina SYN-Morel')
    result = executor(setup).execute('search_clients', {'query': 'SYN-Lina SYN-Morel'})
    assert result['items'] == []


def test_customer_full_name_cannot_bypass_explicit_id_or_invoice_context(setup):
    person = Client.objects.create(company=setup.a, client_type='PP', code_client='PERSON',
        prenom='SYN-Lina', nom='SYN-Morel')
    with pytest.raises(ChatAIError) as caught:
        executor(setup).execute('search_clients', {
            'query': 'SYN-Lina SYN-Morel', 'client_id': setup.client.pk})
    assert caught.value.code == 'NOT_FOUND'
    ex = executor(setup)
    ex.context = {'invoice_id': setup.invoice.pk}
    assert ex.execute('search_clients', {'related_invoice': True})['items'][0]['id'] == setup.client.pk
    assert person.pk not in ex.state['ids']
