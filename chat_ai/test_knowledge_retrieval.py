"""Development retrieval regressions against the actual approved EN/FR corpus.

These include the 20 observed development queries, not held-out model evaluation.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from .knowledge import ChatAIKnowledgeService, tokens
from .models import KnowledgeDocument
from .tests import setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def corpus(setup, settings):
    settings.CHAT_AI_KNOWLEDGE_PATH = str(Path(__file__).with_name('knowledge'))
    call_command('sync_ai_knowledge')
    assert KnowledgeDocument.objects.count() == 12
    return setup


DEVELOPMENT_CASES = [
    ('How can I create a customer invoice?', 'invoice-create'),
    ('Quelles étapes pour créer une facture client ?', 'invoice-create'),
    ('How do I find an old invoice?', 'invoice-find'),
    ('Où chercher une ancienne facture ?', 'invoice-find'),
    ('What permissions do I need to validate an invoice?', 'invoice-validate'),
    ('Qui peut valider une facture ?', 'invoice-validate'),
    ('What does the invoice status mean?', 'invoice-status'),
    ('Explique les statuts des factures.', 'invoice-status'),
    ('What is the difference between revenue and collected payments?', 'financial-definitions'),
    ('Différence entre chiffre d’affaires et encaissements ?', 'financial-definitions'),
    ('How are physical, reserved and available stock related?', 'stock-quantities'),
    ('Comment est calculé le stock disponible ?', 'stock-quantities'),
    ('Where can I search for a product?', 'articles-find'),
    ('Comment rechercher un article ?', 'articles-find'),
    ('Where can I find a logistics order?', 'logistics-find'),
    ('Comment retrouver un dossier logistique ?', 'logistics-find'),
    ('How do I confirm a change or deletion?', 'assistant-actions'),
    ('Comment confirmer une modification ou suppression ?', 'assistant-actions'),
    ('Where can I search for a customer?', 'clients'),
    ('Comment retrouver un client ?', 'clients'),
]


@pytest.mark.parametrize('query,expected', DEVELOPMENT_CASES)
def test_observed_development_questions_retrieve_expected_document(corpus, query, expected):
    hits = ChatAIKnowledgeService().retrieve(query, corpus.a.pk, {'read','create','stock_read','user_admin'})
    assert expected in [hit['document_id'] for hit in hits]


@pytest.mark.parametrize('query,expected', [
    ('Explain invoice statuses please', 'invoice-status'),
    ('Quels sont les STATUTS des FACTURES ?', 'invoice-status'),
    ('Statuts de paiements', 'invoice-status'),
    ('Explain customers and companies', 'clients'),
    ('Des sociétés et des clients', 'clients'),
    ('ECHÉANCES et LIBELLÉS des champs', 'form-labels'),
    ('echeances et libelles des champs', 'form-labels'),
    ('What are payment terms and due dates?', 'form-labels'),
    ('Quels stocks sont disponibles et projetés ?', 'stock-quantities'),
    ('Receipts and inventories', 'stock-quantities'),
    ('Quels comptes utilisateurs sont actifs ?', 'users-find'),
    ('User accounts and administrators', 'users-find'),
    ('Références et désignations des articles', 'articles-find'),
    ('references et designations des articles', 'articles-find'),
    ('Taxes and profits', 'financial-definitions'),
])
def test_plural_and_accent_variants_rank_the_verified_topic_first(corpus, query, expected):
    hits = ChatAIKnowledgeService().retrieve(query, corpus.a.pk, {'read','create','stock_read','user_admin'})
    assert hits[0]['document_id'] == expected


@pytest.mark.parametrize('query', ['', '?! —', 'the and please how', 'les des et pour',
                                   'astrophysics nebulae', 'météorologie quantique'])
def test_empty_function_word_only_and_unknown_queries_have_no_false_workflow(corpus, query):
    assert ChatAIKnowledgeService().retrieve(query, corpus.a.pk, {'read'}) == []


def test_normalization_preserves_singular_words_and_folds_accents():
    assert tokens('status business analysis prix') == {'status','business','analysis','prix'}
    assert tokens('STATUTS factures sociétés éCHÉANCES') == tokens('statut facture societe echeance')
    assert tokens('statuses invoices companies inventories') == tokens('status invoice company inventory')


def test_scope_filters_exclude_private_content_before_tokenization_or_ranking(corpus):
    baseline = ChatAIKnowledgeService().retrieve('Invoice statuses', corpus.a.pk, {'read'})
    for identifier, overrides in [
        ('private-capability', {'required_capabilities':['user_admin']}),
        ('private-tenant', {'tenant_scope_id':corpus.b.pk}),
        ('private-application', {'application_id':'contrat'}),
        ('private-sensitivity', {'sensitivity':'admin'}),
    ]:
        KnowledgeDocument.objects.create(document_id=identifier, document_version='private',
            title='Private invoice statuses ' + identifier, content='Unapproved secret ' + identifier,
            keywords=['invoices','statuses'], category='workflow', **overrides)
    with patch('chat_ai.knowledge.tokens', wraps=tokens) as normalize:
        hits = ChatAIKnowledgeService().retrieve('Invoice statuses', corpus.a.pk, {'read'})
    assert hits == baseline
    assert 'invoice-status' in [hit['document_id'] for hit in hits]
    assert not any(hit['document_id'].startswith('private-') for hit in hits)
    assert all('private-' not in call.args[0] for call in normalize.call_args_list)
    assert not {'invoice-create','invoice-validate','stock-quantities','users-find'} & {hit['document_id'] for hit in hits}
