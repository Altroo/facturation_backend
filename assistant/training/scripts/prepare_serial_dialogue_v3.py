"""Prepare cumulative dialogue curricula; never launch or accept a model.

Frozen prior files remain unchanged. A launcher must require acceptance of the
exact preceding model/dataset before one server-only stage can begin.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from serial_scope_v2 import STAGES, validate_stage, validate_retained_curriculum

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / 'training/datasets'
SOURCES = ('contracts-dialogue-v3-en-fr', 'gestion-magasin-dialogue-v3-en-fr', 'reservation-dialogue-v3-en-fr')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logical_prompt(messages):
    """Unwrap only our generated metadata envelope, never used for runtime trust."""
    value = next(message['content'] for message in reversed(messages) if message['role'] == 'user')
    marker = 'Earlier user messages (background only): '
    if value.startswith(marker):
        history, end = json.JSONDecoder().raw_decode(value[len(marker):])
        suffix = value[len(marker) + end:]
        assert isinstance(history, list) and suffix.startswith('\nCurrent request: ')
        value = suffix[len('\nCurrent request: '):]
    return value


def prompt_key(row):
    app = row.get('application') or row.get('trusted_context', {}).get('application')
    if not app:
        app = json.loads(row['messages'][0]['content'].split('Trusted context: ', 1)[1])['application']
    return app, re.sub(r'\W+', ' ', unicodedata.normalize('NFKD', logical_prompt(row['messages'])).casefold()).strip()


def frozen_rows(relative, info):
    path = ROOT / relative
    assert digest(path) == info['sha256'], relative
    rows = list(map(json.loads, path.read_text().splitlines()))
    assert len(rows) == info['count']
    return rows


def main():
    previous = DATASETS / 'shared-v5r5-en-fr'
    diagnostic = DATASETS / 'shared-dialogue-v1-en-fr'
    baseline_manifest = json.loads((diagnostic / 'manifest.json').read_text())
    assert digest(diagnostic / 'manifest.json') == json.loads((previous / 'manifest.json').read_text())['evaluation_manifest_sha256']
    held = {str((diagnostic / name).relative_to(ROOT)): {'sha256': baseline_manifest['files'][name], 'count': info['count']}
            for name, info in baseline_manifest['inputs'].items()}
    for stage, source_name, version in zip(STAGES, SOURCES, ('shared-v6r5-en-fr', 'shared-v7r5-en-fr', 'shared-v8r5-en-fr')):
        output = DATASETS / version
        if output.exists():
            raise ValueError('Never overwrite a frozen cumulative preparation')
        prior = json.loads((previous / 'manifest.json').read_text())
        source = DATASETS / source_name
        source_manifest = json.loads((source / 'manifest.json').read_text())
        assert source_manifest['application'] == stage and source_manifest['languages'] == ['en', 'fr']
        test = source / 'test.eval.jsonl'
        assert digest(test) == source_manifest['files'][test.name]
        held[str(test.relative_to(ROOT))] = {'sha256': digest(test), 'count': source_manifest['counts']['test']['retained']}
        excluded = {prompt_key(row) for path, info in held.items() for row in frozen_rows(path, info)}
        payloads, keys, counts = {}, {}, {}
        for name in ('train.jsonl', 'valid.jsonl'):
            retained, added = [(directory / name).read_bytes() for directory in (previous, source)]
            assert hashlib.sha256(retained).hexdigest() == prior['files'][name]
            assert hashlib.sha256(added).hexdigest() == source_manifest['files'][name]
            assert retained.endswith(b'\n') and added.endswith(b'\n')
            payloads[name] = retained + added
            rows = list(map(json.loads, payloads[name].splitlines()))
            keys[name] = {prompt_key(row) for row in rows}
            assert not keys[name] & excluded, 'Held-out logical request in optimization data'
            counts[name] = dict(Counter(row['application'] for row in rows))
        assert not keys['train.jsonl'] & keys['valid.jsonl'], 'Logical cross-split overlap'
        manifest = {'version': version, 'applications': prior['applications'] + [stage], 'languages': ['en','fr'],
            'retained_dataset': {'version': previous.name, 'manifest_sha256': digest(previous / 'manifest.json'),
                'files': {name: prior['files'][name] for name in payloads}},
            'added_dataset': {'version': source_name, 'manifest_sha256': digest(source / 'manifest.json'),
                'files': source_manifest['files']}, 'counts': counts,
            'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()},
            'held_out': dict(held), 'held_out_count': sum(info['count'] for info in held.values()),
            'generator_sha256': digest(Path(__file__)),
            'scope_validator_sha256': digest(Path(__file__).with_name('serial_scope_v2.py')),
            'split_policy': 'Retains the preceding train/validation bytes. Appends reviewed synthetic new-app rows in original splits. Neutral-history variants are not independent. Exact normalized logical cross-split and held-out overlap rejected; semantic independence remains limited.',
            'training_status': 'PREPARATION ONLY. Predecessor acceptance, frozen baseline, server preflight and resource gates required. One shared model; no automatic training or activation.'}
        train, valid = [list(map(json.loads, payloads[name].splitlines())) for name in payloads]
        validate_stage(stage, manifest, train, valid, complete_epochs=1)
        validate_retained_curriculum(stage, manifest, payloads['train.jsonl'], payloads['valid.jsonl'], previous)
        for raw in payloads.values():
            assert not re.search(r'[\u0600-\u06ff]|BEGIN.{0,12}PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret)\s*[:=]', raw.decode(), re.I)
        output.mkdir()
        for name, raw in payloads.items():
            (output / name).write_bytes(raw)
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps({'stage': stage, 'train':len(train), 'valid':len(valid), 'held_out':manifest['held_out_count'], 'training_started':False}), flush=True)
        previous = output


if __name__ == '__main__':
    main()
