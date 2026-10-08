"""Reviewed bilingual excerpts: validation, versioning and authorization boundaries."""
import hashlib
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError

from .knowledge import ChatAIKnowledgeService, validate_localized_content
from .models import KnowledgeDocument
from .tests import setup

pytestmark = pytest.mark.django_db

EXCERPTS = {
    'fr': '1. Cliquez sur « Ajouter des articles ».\n2. Vérifiez les montants.',
    'en': '1. Click “Add items”.\n2. Check the amounts.',
}


@pytest.fixture
def source_directory(tmp_path, settings):
    settings.CHAT_AI_KNOWLEDGE_PATH = str(tmp_path)
    return tmp_path


def approved_document(identifier='invoice-workflow', **overrides):
    return {
        'application_id': 'facturation', 'document_id': identifier, 'approved': True,
        'title': 'Invoice workflow', 'category': 'workflow',
        'keywords': ['invoice'], 'content': 'Verified invoice workflow.',
        'required_capabilities': ['read'], 'localized_content': dict(EXCERPTS),
        **overrides,
    }


def write_document(directory, document):
    path = directory / (document['document_id'] + '.json')
    path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    return path


def sync():
    output = StringIO()
    call_command('sync_ai_knowledge', stdout=output)
    return output.getvalue()


def test_localized_text_is_stored_and_returned_verbatim(source_directory, setup):
    document = approved_document()
    write_document(source_directory, document)
    sync()
    stored = KnowledgeDocument.objects.get()
    assert stored.localized_content == EXCERPTS
    hits = ChatAIKnowledgeService().retrieve('invoice', setup.a.pk, {'read'})
    assert hits == [{
        'document_id': stored.pk, 'version': stored.document_version,
        'title': stored.title, 'content': stored.content, 'localized_content': EXCERPTS,
    }]


def test_localized_change_versions_source_and_invalidates_previous_delivery(source_directory, setup):
    document = approved_document()
    path = write_document(source_directory, document)
    sync()
    stored = KnowledgeDocument.objects.get()
    before = (stored.document_version, stored.updated_at)
    sources = [{'document_id': stored.pk, 'version': stored.document_version}]
    assert ChatAIKnowledgeService.sources_authorized(sources, setup.a.pk, {'read'})
    assert 'Updated 0;' in sync()
    stored.refresh_from_db()
    assert (stored.document_version, stored.updated_at) == before

    document['localized_content']['en'] = 'Reviewed revised English procedure.'
    write_document(source_directory, document)
    assert 'Updated 1;' in sync()
    stored.refresh_from_db()
    assert stored.document_version == hashlib.sha256(path.read_bytes()).hexdigest()
    assert stored.document_version != before[0]
    assert stored.localized_content['fr'] == EXCERPTS['fr']
    assert stored.localized_content['en'] == document['localized_content']['en']
    assert not ChatAIKnowledgeService.sources_authorized(sources, setup.a.pk, {'read'})


def test_legacy_absence_is_supported_and_removal_clears_old_excerpt(source_directory, setup):
    document = approved_document()
    write_document(source_directory, document)
    sync()
    old_version = KnowledgeDocument.objects.get().document_version
    document.pop('localized_content')
    write_document(source_directory, document)
    sync()
    stored = KnowledgeDocument.objects.get()
    assert stored.localized_content == {}
    assert stored.document_version != old_version
    assert ChatAIKnowledgeService().retrieve('invoice', setup.a.pk, {'read'})[0]['localized_content'] == {}


@pytest.mark.parametrize('value', [
    None, [], {}, {'fr': 'Texte'}, {'en': 'Text'},
    {'fr': 'Texte', 'en': 'Text', 'ar': 'Texte'},
    {'FR': 'Texte', 'en': 'Text'}, {'fr': 'Texte', 'en-US': 'Text'},
    {'fr': '', 'en': 'Text'}, {'fr': 'Texte', 'en': '   '},
    {'fr': 5, 'en': 'Text'}, {'fr': 'Texte', 'en': False},
    {'fr': ['Texte'], 'en': 'Text'}, {'fr': 'Texte', 'en': {'text': 'Text'}},
    {'fr': 'x' * 6001, 'en': 'Text'}, {'fr': 'Texte', 'en': 'x' * 6001},
    {'fr': 'Texte\x00', 'en': 'Text'},
])
def test_invalid_localized_contract_rejected_before_any_database_changes(source_directory, value):
    KnowledgeDocument.objects.create(document_id='retained', document_version='old',
        title='Retained', content='Existing content', category='workflow')
    write_document(source_directory, approved_document('a-valid'))
    write_document(source_directory, approved_document('z-invalid', localized_content=value))
    with pytest.raises(CommandError, match='Invalid or sensitive localized content'):
        sync()
    assert list(KnowledgeDocument.objects.values_list('pk', 'content')) == [('retained', 'Existing content')]


@pytest.mark.parametrize('locale', ['fr', 'en'])
@pytest.mark.parametrize('sensitive', [
    'password: synthetic-private-value',
    'api_key=synthetic-private-value',
    'access_token: synthetic-private-value',
    'Bearer synthetic_private_token_123',
    '-----BEGIN PRIVATE KEY-----',
])
def test_decoded_localized_secrets_rejected_without_echoing_payload(source_directory, locale, sensitive):
    document = approved_document()
    document['localized_content'][locale] = sensitive
    path = write_document(source_directory, document)
    # Encode every secret character so scanning only the raw JSON cannot catch it.
    encoded = ''.join('\\u%04x' % ord(character) for character in sensitive)
    raw = path.read_text()
    path.write_text(raw.replace(json.dumps(sensitive), '"' + encoded + '"'))
    assert json.loads(path.read_text())['localized_content'][locale] == sensitive
    with pytest.raises(CommandError) as error:
        sync()
    assert sensitive not in str(error.value)
    assert not KnowledgeDocument.objects.exists()


def test_exact_locale_limits_are_preserved_without_truncating_procedures(source_directory, setup):
    value = {'fr': 'é' * 6000, 'en': 'x' * 6000}
    write_document(source_directory, approved_document(localized_content=value))
    sync()
    assert KnowledgeDocument.objects.get().localized_content == value
    assert ChatAIKnowledgeService().retrieve('invoice', setup.a.pk, {'read'})[0]['localized_content'] == value


@pytest.mark.parametrize('scope', ['global', 'own_tenant', 'foreign_tenant', 'capability', 'sensitivity', 'application'])
def test_permission_filters_apply_before_reading_localized_excerpts(setup, scope):
    overrides = {
        'global': {}, 'own_tenant': {'tenant_scope': setup.a},
        'foreign_tenant': {'tenant_scope': setup.b},
        'capability': {'required_capabilities': ['user_admin']},
        'sensitivity': {'sensitivity': 'admin'},
        'application': {'application_id': 'contrat'},
    }[scope]
    fields = dict(document_id='scoped', document_version='1', title='Invoice',
                  content='Invoice workflow', category='workflow', keywords=['invoice'],
                  required_capabilities=['read'], localized_content=EXCERPTS)
    fields.update(overrides)
    KnowledgeDocument.objects.create(**fields)
    with patch('chat_ai.knowledge.validate_localized_content', wraps=validate_localized_content) as validate:
        hits = ChatAIKnowledgeService().retrieve('invoice', setup.a.pk, {'read'})
    if scope in {'global', 'own_tenant'}:
        assert hits[0]['localized_content'] == EXCERPTS
        validate.assert_called_once_with(EXCERPTS)
    else:
        assert hits == []
        validate.assert_not_called()


@pytest.mark.parametrize('value', [
    {}, None, {'fr': 'Texte'}, {'fr': 'Texte', 'en': []},
    {'fr': 'Texte', 'en': 'x' * 6001},
    {'fr': 'Texte', 'en': 'password=synthetic-private-value'},
    {'fr': 'Texte', 'en': 'Text', 'unexpected': 'hidden'},
])
def test_malformed_direct_database_excerpts_fail_closed(setup, value):
    # JSON null is not a SQL NULL; simulate it through a non-null JSON container update.
    from django.db.models import Value, JSONField
    document = KnowledgeDocument.objects.create(document_id='bad-direct-edit',
        document_version='1', title='Invoice', content='Legacy verified invoice content',
        category='workflow', required_capabilities=['read'], keywords=['invoice'])
    KnowledgeDocument.objects.filter(pk=document.pk).update(localized_content=Value(value, output_field=JSONField()))
    hits = ChatAIKnowledgeService().retrieve('invoice', setup.a.pk, {'read'})
    assert hits[0]['localized_content'] == {}
    assert hits[0]['content'] == document.content


def test_all_twelve_approved_documents_sync_with_both_reviewed_languages(settings):
    source = Path(__file__).with_name('knowledge')
    settings.CHAT_AI_KNOWLEDGE_PATH = str(source)
    assert 'approved 12.' in sync()
    assert KnowledgeDocument.objects.count() == 12
    for document in KnowledgeDocument.objects.all():
        assert validate_localized_content(document.localized_content) == document.localized_content
    create = KnowledgeDocument.objects.get(pk='invoice-create')
    for locale, captions in {
        'fr': ['Nouvelle facture client', 'Date de la facture', 'Ajouter des articles',
               'Lignes de la facture', 'Ajouter article', 'Mettre à jour'],
        'en': ['New client invoice', 'Invoice date', 'Add items', 'Invoice lines', 'Add article', 'Update'],
    }.items():
        text = create.localized_content[locale]
        for caption in captions:
            assert caption in text
        for step in range(1, 7):
            assert '\n' + str(step) + '. ' in text
    assert 'HT signifie hors taxes.' in create.localized_content['fr']
    assert 'TVA signifie taxe sur la valeur ajoutée.' in create.localized_content['fr']
    assert 'TTC signifie toutes taxes comprises.' in create.localized_content['fr']
    assert 'HT means excluding tax.' in create.localized_content['en']
    assert 'TVA means value-added tax (VAT).' in create.localized_content['en']
    assert 'TTC means including tax.' in create.localized_content['en']
