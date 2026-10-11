"""Freeze EN/FR saved-result planner checks using native permission-filtered tools.

Run with the Management Projet backend and shared package on PYTHONPATH. Only
synthetic context is authored; every database connection is explicitly forbidden.
No training split is generated. Model inference is a separate server-only step.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'management_projet_backend.settings_ai_test')
import django
from django.db import connections

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'training/datasets/management-projet-followup-v1-en-fr'


def deny_database(*args, **kwargs):
    raise RuntimeError('Synthetic follow-up evaluation cannot access a database')


def main():
    with contextlib.ExitStack() as guard:
        for connection in connections.all():
            guard.enter_context(connection.execute_wrapper(deny_database))
        django.setup()
        from chat_ai.planner import SYSTEM, shortlist
        from chat_ai.tools import registry
        from chat_ai.security import SECRET
        from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
        from chat_ai_assistant.calendar_context import with_calendar_context
        from jsonschema import validate
        import chat_ai.services
        import chat_ai.planner
        import chat_ai.tools
        native = registry()
        rows = []

        def add(key, resource, ids, fr, en, tool, arguments, *, caps=None, history=None):
            for language, question in [('fr', fr), ('en', en)]:
                context = {'application': 'management_projet', 'today': '2035-04-09',
                    'currency_default': 'MAD', 'capabilities': caps or ['read', 'print', 'create', 'update', 'delete'],
                    'interface_language': 'en' if language == 'fr' else 'fr',
                    'current_resource': None, 'current_identifier': None,
                    'previous_result_type': resource if ids else None,
                    'previous_result_count': len(ids), 'previous_result_identifiers': ids}
                args = dict(arguments)
                if tool == 'clarify':
                    args['language'] = language
                    validate(args, CLARIFICATION_SCHEMA)
                selected = shortlist(question, native.permitted(set(context['capabilities'])), context)
                if tool != 'clarify':
                    definition = next(item for item in selected if item.name == tool)
                    validate(args, definition.input_schema)
                context = with_calendar_context(context)
                messages = [{'role': 'system', 'content': SYSTEM + '\nTrusted context: ' + json.dumps(context, ensure_ascii=False)}]
                if history:
                    messages.append({'role': 'user', 'content': history})
                messages.append({'role': 'user', 'content': question})
                row = {'id': key + '-' + language, 'category': key, 'language': language,
                       'messages': messages, 'offered_tool_schemas': [item.schema() for item in selected],
                       'expected': {'tool': tool, 'arguments': args}}
                assert not SECRET.search(json.dumps(row, ensure_ascii=False))
                rows.append(row)

        edits = [
            ('second-customer-city', 'client', [2187, 904, 6312], 1,
             'Modifie la ville du deuxième client trouvé en Dakhla.',
             'Change the second customer result’s city to Dakhla.', {'ville': 'Dakhla'}),
            ('first-supplier-contact', 'supplier', [5834, 227, 4081], 0,
             'Modifie le contact du premier fournisseur en « Contact Synthétique ».',
             'Update the first supplier’s contact to “Contact Synthétique”.', {'contact': 'Contact Synthétique'}),
            ('third-project-status', 'project', [311, 8092, 1456], 2,
             'Modifie le troisième projet : statut En pause.',
             'Update the third project: status Paused.', {'status': 'En pause'}),
            ('second-quote-amount', 'quote', [7754, 362, 5901], 1,
             'Modifie le montant HT du deuxième devis à 54.75.',
             'Change the second quote’s amount excluding VAT to 54.75.', {'amount_ht': '54.75'}),
            ('third-expense-note', 'expense', [4302, 7921, 185], 2,
             'Modifie les notes de la troisième dépense en « Contrôle synthétique ».',
             'Edit the third expense’s notes to “Contrôle synthétique”.', {'notes': 'Contrôle synthétique'}),
            ('first-receipt-date', 'revenue', [6173, 835, 2984], 0,
             'Modifie la date du premier encaissement au 2035-05-17.',
             'Change the first receipt’s date to 2035-05-17.', {'date': '2035-05-17'}),
            ('second-schedule-date', 'payment_schedule', [728, 5543, 3691], 1,
             'Modifie la date d’échéance du deuxième résultat au 2035-06-21.',
             'Change the second result’s due date to 2035-06-21.', {'due_date': '2035-06-21'}),
            ('third-budget-stage', 'budget_entry', [8014, 452, 2863], 2,
             'Modifie l’étape de la troisième ligne de budget réel en « Isolation test ».',
             'Edit the third actual-budget entry’s stage to “Isolation test”.', {'stage': 'Isolation test'}),
        ]
        for key, resource, ids, index, fr, en, changes in edits:
            add(key, resource, ids, fr, en, 'prepare_change',
                {'resource': resource, 'identifier': ids[index], 'operation': 'update', 'changes': changes})
        add('third-customer-delete', 'client', [5762, 819, 3047],
            'Supprime le troisième client des résultats.', 'Delete the third customer in the results.',
            'prepare_change', {'resource': 'client', 'identifier': 3047, 'operation': 'delete'})
        add('second-result-after-other-language', 'client', [4182, 937, 6501],
            'Modifie l’adresse du deuxième résultat en « Adresse de test ».',
            'Change the second result’s address to “Adresse de test”.', 'prepare_change',
            {'resource': 'client', 'identifier': 937, 'operation': 'update', 'changes': {'adresse': 'Adresse de test'}},
            history='Affiche les clients trouvés. Show the matching customers.')
        add('out-of-range', 'client', [7612, 339],
            'Modifie la ville du troisième résultat en Laâyoune.',
            'Change the third result’s city to Laâyoune.', 'clarify', {'reason': 'missing_details'})
        add('expired-selection', None, [],
            'Modifie la ville du deuxième résultat en Laâyoune.',
            'Change the second result’s city to Laâyoune.', 'clarify', {'reason': 'missing_details'},
            history='Find customers named “SYN-Customer-Test”.')
        add('read-only-selection', 'client', [2064, 8973],
            'Modifie la ville du premier résultat en Laâyoune.',
            'Change the first result’s city to Laâyoune.', 'clarify', {'reason': 'unsupported'}, caps=['read'])
        add('delete-no-selection', None, [],
            'Supprime le deuxième résultat.', 'Delete the second result.',
            'clarify', {'reason': 'missing_details'})

        assert len(rows) == 28 and len({row['id'] for row in rows}) == len(rows)
        questions = {row['messages'][-1]['content'].casefold().strip() for row in rows}
        assert len(questions) == len(rows)
        for dataset in (ROOT / 'training/datasets').glob('*/*.jsonl'):
            if dataset.parent == OUT:
                continue
            for line in dataset.read_text().splitlines():
                previous = json.loads(line)
                for message in previous.get('messages', []):
                    if message.get('role') == 'user':
                        assert message['content'].casefold().strip() not in questions, ('Existing prompt', dataset.name)
        payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
        sources = {str(Path(module.__file__).relative_to(Path(chat_ai.tools.__file__).parents[1])):
                   hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                   for module in [chat_ai.services, chat_ai.planner, chat_ai.tools]}
        manifest = {'version': OUT.name, 'application': 'management_projet', 'languages': ['en', 'fr'],
                    'count': len(rows), 'status': 'Unmeasured diagnostic; no training or acceptance claim.',
                    'methodology': 'Synthetic fresh cases for saved-result ordinal edits and safe clarification. Current native prompt and permission-filtered registry. No business operations are executed by evaluation. All database access prohibited during generation. Neither train nor validation examples are generated.',
                    'files': {'independent.eval.jsonl': hashlib.sha256(payload.encode()).hexdigest()},
                    'native_sources': sources,
                    'shared_sources': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in [ROOT / 'src/chat_ai_assistant/calendar_context.py', ROOT / 'src/chat_ai_assistant/orchestrator.py']},
                    'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        if OUT.exists():
            assert (OUT / 'independent.eval.jsonl').read_text() == payload
            assert json.loads((OUT / 'manifest.json').read_text()) == manifest
        else:
            OUT.mkdir()
            (OUT / 'independent.eval.jsonl').write_text(payload)
            (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'count': len(rows), 'database_access': 'prohibited', 'model_inference': 'not run'}))


if __name__ == '__main__':
    main()
