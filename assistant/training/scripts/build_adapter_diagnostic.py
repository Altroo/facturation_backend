"""Rebind frozen synthetic scenarios to current native planner metadata.

Run once per application with its backend on PYTHONPATH and isolated Django
settings. This creates a separate diagnostic: old labels/files are never edited.
No model or database access occurs. The follow-up set remains separate.
"""
import argparse
import contextlib
import copy
import hashlib
import json
from pathlib import Path

import django
from django.db import connections

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'training/datasets/shared-adapter-v2-en-fr'
PREFIX = {'facturation': 'facturation', 'management_projet': 'management-projet', 'design_workflow': 'design-workflow'}


def deny_database(*args, **kwargs):
    raise RuntimeError('Adapter diagnostics must not access a database')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--application', choices=PREFIX, required=True)
    app = parser.parse_args().application
    with contextlib.ExitStack() as guard:
        for connection in connections.all():
            guard.enter_context(connection.execute_wrapper(deny_database))
        django.setup()
        import chat_ai.tools
        from chat_ai_assistant.calendar_context import with_calendar_context
        from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
        from jsonschema import validate
        if app == 'facturation':
            from chat_ai_assistant.orchestrator import SYSTEM
            from chat_ai_assistant.routing import shortlist
            from chat_ai.shortcut_catalog import shortcut_search_hint
        else:
            from chat_ai.planner import SYSTEM, shortlist
        native = chat_ai.tools.registry()
        parent = json.loads((ROOT / 'training/datasets/shared-metadata-v1-en-fr/manifest.json').read_text())
        source_files = [Path(chat_ai.tools.__file__)]
        for name in ('planner.py', 'services.py', 'shortcuts.py'):
            path = source_files[0].parent / name
            if path.is_file():
                source_files.append(path)
        sources = {str(path.relative_to(source_files[0].parents[1])): digest(path) for path in source_files}
        shared = {str(path.relative_to(ROOT)): digest(path) for path in [
            ROOT / 'src/chat_ai_assistant/orchestrator.py', ROOT / 'src/chat_ai_assistant/calendar_context.py',
            ROOT / 'src/chat_ai_assistant/routing.py', ROOT / 'training/scripts/build_refinement_v1.py',
            ROOT / 'training/scripts/build_dataset_v4.py']}
        manifest = {'version': OUT.name, 'application': app, 'languages': ['en', 'fr'],
            'status': 'Unmeasured current-adapter diagnostic; no training or acceptance claim.',
            'methodology': 'Original user prompts and expected actions unchanged. Current native system prompt and permission-filtered tool schemas replace historical envelopes. Historical DW capability snapshots gain the native mutate alias when update/archive is present; historical role-profile labels are not a live role simulation. Backend role authorization is tested separately. Calendar anchors are computed from the original trusted date. Synthetic saved IDs are added to four legacy ordinal-opening scenarios that recorded only result count; these IDs do not change their expected ordinal. No business tools execute. Previously reviewed regressions are not unseen certification.',
            'native_sources': sources, 'shared_sources': shared,
            'generator_sha256': digest(Path(__file__)), 'files': {}, 'inputs': {}, 'count': 0}
        payloads = {}
        for name, info in parent['inputs'].items():
            if not info['original_dataset'].startswith(PREFIX[app]):
                continue
            path = ROOT / 'training/datasets' / info['original_dataset']
            assert digest(path) == info['original_sha256']
            originals = [json.loads(line) for line in path.read_text().splitlines()]
            rows = []
            for original in originals:
                row = copy.deepcopy(original)
                context = json.loads(original['messages'][0]['content'].split('Trusted context: ', 1)[1])
                text = original['messages'][-1]['content']
                caps = original.get('capabilities', context.get('capabilities'))
                if caps is None and app == 'facturation':
                    assert info['original_dataset'] == 'facturation-refinement-v1-en-fr/independent.eval.jsonl'
                    # That generator omitted caps from rows but used member_edit for every independent case.
                    source_manifest = json.loads((path.parent / 'manifest.json').read_text())
                    assert source_manifest['generator_sha256'] == digest(ROOT / 'training/scripts/build_refinement_v1.py')
                    from build_dataset_v4 import PROFILES
                    caps = PROFILES['member_edit']
                assert caps is not None, ('Missing synthetic capability profile', row['id'])
                if app == 'design_workflow':
                    # Native capabilities derives this alias from existing write flags.
                    caps = sorted(set(caps) | ({'mutate'} if set(caps) & {'update', 'archive'} else set()))
                    context['capabilities'] = caps
                if app == 'facturation':
                    hint = shortcut_search_hint(text)
                    if hint != text:
                        context['shortcut_search_hint'] = hint
                else:
                    context.setdefault('current_resource', None)
                    context.setdefault('current_identifier', None)
                if app == 'management_projet':
                    count = context.get('previous_result_count', 0)
                    if count and 'previous_result_identifiers' not in context:
                        assert row['expected']['tool'] == 'previous_results' and count == 3
                        context['previous_result_identifiers'] = [8101, 4107, 9053]
                    context.setdefault('previous_result_identifiers', [])
                selected = shortlist(context.get('shortcut_search_hint') or text, native.permitted(set(caps)), context)
                expected = row['expected']
                if expected['tool'] == 'clarify':
                    validate(expected['arguments'], CLARIFICATION_SCHEMA)
                else:
                    definition = next((tool for tool in selected if tool.name == expected['tool']), None)
                    assert definition is not None, ('Frozen target no longer offered', row['id'])
                    validate(expected['arguments'], definition.input_schema)
                context = with_calendar_context(context)
                row['trusted_context'] = context
                row['offered_tools'] = [tool.name for tool in selected]
                row['offered_tool_schemas'] = [tool.schema() for tool in selected]
                row['messages'][0] = {'role': 'system', 'content': SYSTEM + '\nTrusted context: ' + json.dumps(context, ensure_ascii=False)}
                assert row['messages'][1:] == original['messages'][1:] and row['expected'] == original['expected']
                rows.append(row)
            payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
            payloads[name] = payload
            manifest['files'][name] = hashlib.sha256(payload.encode()).hexdigest()
            manifest['inputs'][name] = {**info, 'current_adapter': True}
            manifest['count'] += len(rows)
        assert manifest['count'] == {'facturation': 92, 'management_projet': 156, 'design_workflow': 114}[app]
        OUT.mkdir(exist_ok=True)
        payloads['manifest-' + app + '.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        for name, payload in payloads.items():
            path = OUT / name
            if path.exists():
                assert path.read_text() == payload, ('Do not overwrite a frozen diagnostic', name)
            else:
                with path.open('x') as stream:
                    stream.write(payload)
        print(json.dumps({'application': app, 'count': manifest['count'], 'database_access': 'prohibited', 'model_inference': 'not run'}))


if __name__ == '__main__':
    main()
