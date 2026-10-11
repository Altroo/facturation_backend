"""Version conversation framing without changing a frozen question or target.

Uses the same shared input builder as native adapters. Augmentation adds only
neutral greeting/thanks background to already-approved SFT examples. Held-out
scenarios are never copied into SFT; diagnostics preserve their original labels.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from chat_ai_assistant.planning_messages import planning_messages
from chat_ai_assistant.clarifications import message_language


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(rows):
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)


def reframe(messages):
    result = deepcopy(messages)
    if len(result) < 2 or result[0]['role'] != 'system':
        raise ValueError('Expected native system prompt')
    target = result.pop() if result[-1]['role'] == 'assistant' else None
    if any(message['role'] != 'user' for message in result[1:]):
        raise ValueError('Unexpected planner history role')
    if len(result) > 2:
        result = [result[0], planning_messages('', {}, result[-1]['content'], result[1:-1])[-1]]
    if target is not None:
        result.append(target)
    return result


def augment(rows, per_group):
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        if len(row['messages']) != 3:
            continue
        target = row['messages'][-1]['tool_calls'][0]['function']['name']
        language = message_language(row['messages'][1]['content'], 'fr')
        groups[(row['application'], target, language)].append(index)
    extra, provenance = [], []
    greetings = ('Bonjour, merci pour votre aide.', 'Hello, thanks for your help.')
    for group, indexes in sorted(groups.items()):
        # Stable selection across the entire group, independent of evaluation outcomes.
        indexes.sort(key=lambda index: hashlib.sha256(encode([rows[index]]).encode()).hexdigest())
        for offset, index in enumerate(indexes[:per_group]):
            row = deepcopy(rows[index])
            history = {'role': 'user', 'content': greetings[offset % len(greetings)]}
            row['messages'].insert(1, history)
            row['messages'] = reframe(row['messages'])
            extra.append(row)
            provenance.append({'source_index': index, 'history': history['content'], 'application': group[0]})
    return extra, provenance


def write_dataset(folder, payloads, manifest):
    if folder.exists():
        raise ValueError('Never overwrite a versioned dataset')
    folder.mkdir()
    for name, raw in payloads.items():
        (folder / name).write_text(raw)
    manifest['files'] = {name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in payloads.items()}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parent = ROOT / 'training/datasets/shared-v5r3-en-fr'
    manifest = json.loads((parent / 'manifest.json').read_text())
    common = {'languages': ['en', 'fr'], 'applications': manifest['applications'],
              'generator_sha256': digest(Path(__file__)),
              'planning_messages_sha256': digest(ROOT / 'src/chat_ai_assistant/planning_messages.py'),
              'parent_manifest_sha256': digest(parent / 'manifest.json')}
    diagnostic = ROOT / 'training/datasets/shared-dialogue-v1-en-fr'
    payloads, inputs, changed = {}, {}, []
    for relative, info in manifest['held_out'].items():
        path = ROOT / relative
        assert digest(path) == info['sha256']
        rows = list(map(json.loads, path.read_text().splitlines()))
        filename = path.parent.name + '--' + path.name
        changes = []
        for row in rows:
            before = deepcopy(row['messages'])
            row['messages'] = reframe(before)
            if row['messages'] != before:
                changes.append(row['id'])
                changed.append(row)
        payloads[filename] = encode(rows)
        inputs[filename] = {'source': relative, 'source_sha256': digest(path), 'count': len(rows),
                            'baseline_label': info['baseline_label'], 'changed_ids': changes}
    payloads['changed.eval.jsonl'] = encode(changed)
    write_dataset(diagnostic, payloads, {**common, 'version': diagnostic.name, 'inputs': inputs,
        'count': sum(value['count'] for value in inputs.values()), 'changed_count': len(changed),
        'policy': 'Same frozen user questions, context, offered tools and expected actions; only history framing changes. Reuse unchanged inputs only with matching prior dataset, provider and candidate identity. Changed cases require fresh measurement. No performance certification from a combined reused report.'})
    output = ROOT / 'training/datasets/shared-v5r4-en-fr'
    payloads, counts, augmentation = {}, {}, {}
    for split, per_group in [('train', 2), ('valid', 1)]:
        path = parent / (split + '.jsonl')
        assert digest(path) == manifest['files'][path.name]
        original = list(map(json.loads, path.read_text().splitlines()))
        rows = [{**row, 'messages': reframe(row['messages'])} for row in original]
        extra, provenance = augment(original, per_group)
        payloads[path.name] = encode(rows + extra)
        counts[split] = {'retained': len(rows), 'reframed': sum(a['messages'] != b['messages'] for a, b in zip(original, rows)),
                         'augmented': len(extra), 'total': len(rows) + len(extra)}
        augmentation[split] = provenance
    write_dataset(output, payloads, {**common, 'version': output.name, 'counts': counts,
        'source_files': manifest['files'], 'augmentation': augmentation,
        'evaluation_manifest_sha256': digest(diagnostic / 'manifest.json'),
        'split_policy': 'Retains every reviewed V5r3 logical example and split; transforms history with the production input builder. Adds bounded neutral-history variants of training/validation examples within their original split. These variants are not independent examples. No held-out labels used for augmentation or optimizer selection.',
        'training_policy': 'Server-only continuation of one shared model. Not trained or accepted by dataset generation. No automatic activation.'})
    print(json.dumps({'diagnostic_cases': sum(value['count'] for value in inputs.values()), 'changed_cases': len(changed), 'sft': counts}))


if __name__ == '__main__':
    main()
