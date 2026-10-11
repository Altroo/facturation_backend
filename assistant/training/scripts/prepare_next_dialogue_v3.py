"""Prepare a future native adapter's data for the shared dialogue input format.

Preserves original synthetic questions, actions and splits. No database access,
inference, optimizer or production change. Existing datasets are never replaced.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
APPLICATIONS = {'contrat': ('contracts', 'contracts'), 'gestion_magasin': ('gestion-magasin', 'gestion_magasin'),
                'reservation': ('reservation', 'reservation')}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--application', choices=APPLICATIONS, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    args = parser.parse_args()
    prefix, package = APPLICATIONS[args.application]
    source = ROOT / 'training/datasets' / (prefix + '-v1-en-fr')
    output = ROOT / 'training/datasets' / (prefix + '-dialogue-v3-en-fr')
    if output.exists():
        raise ValueError('Never overwrite frozen preparation')
    prior = json.loads((source / 'manifest.json').read_text())
    sys.path[:0] = [str(ROOT / 'src'), str(args.backend)]
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', package + '_backend.settings_release_test')
    from django.db.backends.base.base import BaseDatabaseWrapper
    def deny_database(*args, **kwargs):
        raise RuntimeError('Synthetic metadata preparation cannot access a database')
    BaseDatabaseWrapper.ensure_connection = deny_database
    import django
    django.setup()
    from chat_ai import tools, planner, targets
    from chat_ai_assistant.calendar_context import with_calendar_context
    from chat_ai_assistant.planning_messages import planning_messages
    from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA, message_language
    from training_contracts import CLARIFICATION_DESCRIPTION
    from jsonschema import validate
    from build_dialogue_v1 import encode, augment, reframe
    from prepare_shared_v5r5 import rebalance, distribution
    clarify = {'type': 'function', 'function': {'name': 'clarify', 'description': CLARIFICATION_DESCRIPTION, 'parameters': CLARIFICATION_SCHEMA}}
    native = tools.registry()
    payloads, counts, provenance, reference_fixtures, history_audit = {}, {}, {}, {}, {}
    for split in ('train', 'valid', 'test'):
        path = source / (split + '.eval.jsonl')
        assert digest(path) == prior['files'][path.name]
        original = list(map(json.loads, path.read_text().splitlines()))
        rebound, training = [], []
        for old in original:
            row = deepcopy(old)
            text = old['messages'][-1]['content']
            context = deepcopy(old['trusted_context'])
            assert context['application'] == args.application
            # Match the current native conversation service, including language switches.
            context['interface_language'] = message_language(text, context.get('interface_language', 'fr'))
            count = context.get('previous_result_count', 0)
            if count:
                assert type(count) is int and 1 <= count <= 10 and context.get('previous_result_type')
                # Old synthetic cases specified count/type only. Supply synthetic,
                # nonsequential IDs in display order, matching validated native context.
                fixture_key = row['id'].rsplit('-', 1)[0]
                ids = [int(hashlib.sha256((fixture_key + ':' + str(index)).encode()).hexdigest()[:7], 16) + 1 for index in range(count)]
                assert len(set(ids)) == count
                context['previous_result_identifiers'] = ids
                reference_fixtures[row['id']] = ids
            else:
                context.update(previous_result_type=None, previous_result_count=0, previous_result_identifiers=[])
            selected = planner.shortlist(text, native.permitted(set(context['capabilities'])), context)
            expected = old['expected']
            if expected['tool'] == 'clarify':
                validate(expected['arguments'], CLARIFICATION_SCHEMA)
            else:
                definition = next((tool for tool in selected if tool.name == expected['tool']), None)
                if definition is None:
                    raise ValueError('Original action absent from current native shortlist: ' + row['id'])
                validate(expected['arguments'], definition.input_schema)
                if expected['tool'] == 'prepare_change':
                    arguments = expected['arguments']
                    assert targets.trusted_target(arguments['resource'], arguments['identifier'], instruction=text,
                        context={'resource': context.get('current_resource'), 'identifier': context.get('current_identifier')},
                        state={}, now=datetime.now(timezone.utc)), row['id']
            context = with_calendar_context(context)
            row.update(trusted_context=context, offered_tools=[tool.name for tool in selected],
                offered_tool_schemas=[tool.schema() for tool in selected],
                messages=planning_messages(planner.SYSTEM, context, text, old['messages'][1:-1]))
            assert row['expected'] == old['expected']
            rebound.append(row)
            # Keep authoritative source roles until neutral-history balancing.
            # Native system/context was rebuilt above; current text and genuine
            # history come directly from the pinned original, never string parsing.
            training.append({'application': args.application,
                'messages': [row['messages'][0], *deepcopy(old['messages'][1:]),
                {'role': 'assistant', 'content': None, 'tool_calls': [{'type': 'function', 'function':
                    {'name': expected['tool'], 'arguments': expected['arguments']}}]}],
                'tools': row['offered_tool_schemas'] + [clarify]})
        payloads[split + '.eval.jsonl'] = encode(rebound)
        counts[split] = {'retained': len(rebound)}
        if split != 'test':
            # Augment the approved single-turn originals, not already wrapped histories.
            eligible = [row for old, row in zip(original, training) if len(old['messages']) == 2]
            framed_extra, provenance[split] = augment(eligible, 2 if split == 'train' else 1)
            extra = []
            for frozen, entry in zip(framed_extra, provenance[split]):
                row = deepcopy(eligible[entry['source_index']])
                row['messages'].insert(1, {'role': 'user', 'content': entry['history']})
                if {**row, 'messages': reframe(row['messages'])} != frozen:
                    raise ValueError('Neutral augmentation reconstruction mismatch')
                extra.append(row)
            provenance[split] = [{**entry, 'source_id': [old['id'] for old in original if len(old['messages']) == 2][entry['source_index']]} for entry in provenance[split]]
            balanced, assignment = rebalance(training + extra)
            for before, after in zip(training + extra, balanced):
                if before['messages'][0] != after['messages'][0] or before['messages'][-2:] != after['messages'][-2:] or before['tools'] != after['tools']:
                    raise ValueError('Neutral balancing changed trusted inputs or labels')
            history_audit[split] = {'distribution': distribution(balanced), 'assignment': assignment}
            payloads[split + '.jsonl'] = encode([{**row, 'messages': reframe(row['messages'])} for row in balanced])
            counts[split].update(augmented=len(extra), total=len(balanced))
    for raw in payloads.values():
        if re.search(r'[\u0600-\u06ff]|BEGIN.{0,12}PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret)\s*[:=]', raw, re.I):
            raise ValueError('Sensitive or unsupported-language content')
    native_paths = [args.backend / 'chat_ai' / name for name in ('tools.py', 'planner.py', 'targets.py', 'services.py', 'security.py', 'resources.py', 'navigation.py')]
    if args.application == 'contrat':
        native_paths.append(args.backend / 'core/constants.py')
    manifest = {'version': output.name, 'application': args.application, 'languages': ['en', 'fr'],
        'source_dataset': source.name, 'source_manifest_sha256': digest(source / 'manifest.json'),
        'source_files': prior['files'], 'counts': counts, 'augmentation': provenance, 'neutral_history': history_audit,
        'synthetic_reference_fixtures': reference_fixtures,
        'generator_sha256': digest(Path(__file__)),
        'native_sources': {str(path.relative_to(args.backend)): digest(path) for path in native_paths},
        'shared_sources': {name: digest(ROOT / name) for name in ('src/chat_ai_assistant/planning_messages.py', 'src/chat_ai_assistant/calendar_context.py', 'src/chat_ai_assistant/clarifications.py', 'src/chat_ai_assistant/contracts.py', 'src/chat_ai_assistant/selection_context.py', 'src/chat_ai_assistant/routing.py', 'training/scripts/build_dialogue_v1.py', 'training/scripts/training_contracts.py', 'training/scripts/prepare_shared_v5r5.py', 'training/scripts/build_shared_v5r3.py')},
        'files': {name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in payloads.items()},
        'policy': 'Original synthetic questions, action labels and split membership retained; current native tools, context and production dialogue framing replace old envelopes. Neutral histories use input-only hashes independent of target labels; genuine history remains intact. Neutral history variants are not independent samples. No model score or training claim. Database connections forbidden.'}
    output.mkdir()
    for name, raw in payloads.items():
        (output / name).write_text(raw)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'application': args.application, 'counts': counts, 'training_started': False}))


if __name__ == '__main__':
    main()
