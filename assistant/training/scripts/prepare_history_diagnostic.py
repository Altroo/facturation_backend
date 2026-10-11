"""Freeze a diagnostic of planner history formatting, without training or inference.

Sources and labels stay immutable. Current-only removes history solely as a
diagnostic ablation, never as an implemented memory or authorization policy.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from build_dialogue_v1 import reframe

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'training/datasets/shared-dialogue-v1-en-fr'
OUTPUT = ROOT / 'training/datasets/planner-history-v1-en-fr'
ARMS = ('original', 'current_only', 'long_greeting', 'current_first')
PAIRS = (
    'facturation-refinement-v2-en-fr-composed-relative',
    'management-projet-refinement-v2-en-fr-multi-field-position',
    'design-workflow-refinement-v2-en-fr-person-and-status',
    'second-result-after-other-language',
    'facturation-refinement-v2-en-fr-quote-limited-state',
    'acceptance-missing_year_switch',
)
IDS = tuple(prefix + '-' + language for prefix in PAIRS for language in ('fr', 'en'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(frozen, source, arm):
    """Read source role boundaries, never parse user-supplied envelope labels."""
    if arm not in ARMS:
        raise ValueError('Unknown history arm')
    messages = source['messages']
    if (len(messages) < 3 or messages[0]['role'] != 'system'
            or any(m['role'] != 'user' or not isinstance(m['content'], str)
                   for m in messages[1:])):
        raise ValueError('Expected native system and separate user turns')
    if reframe(messages) != frozen['messages']:
        raise ValueError('Source turns do not reproduce frozen input')
    if source['expected'] != frozen['expected']:
        raise ValueError('Frozen target differs from source')
    result = deepcopy(frozen)
    if arm == 'original':
        return result
    current = messages[-1]['content']
    history = [m['content'] for m in messages[1:-1]]
    if arm == 'current_only':
        content = current
    elif arm == 'long_greeting':
        replacements = {'Hello': 'Hello, thanks for your help.',
                        'Bonjour': 'Bonjour, merci pour votre aide.'}
        # Only exact neutral greetings change. Genuine task history stays exact.
        history = [replacements.get(value, value) for value in history]
        content = ('Earlier user messages (background only): '
                   + json.dumps(history, ensure_ascii=False)
                   + '\nCurrent request: ' + current)
    else:
        content = ('Current request: ' + current
                   + '\nEarlier user messages (background only): '
                   + json.dumps(history, ensure_ascii=False))
    result['messages'][1]['content'] = content
    return result


def prepare(source=SOURCE, output=OUTPUT):
    if output.exists():
        raise ValueError('Never overwrite a versioned diagnostic')
    manifest = json.loads((source / 'manifest.json').read_text())
    frozen, originals, sources = {}, {}, {}
    for name, info in manifest['inputs'].items():
        path = source / name
        original = ROOT / info['source']
        if sha(path) != manifest['files'][name] or sha(original) != info['source_sha256']:
            raise ValueError('Frozen source changed')
        values = {row['id']: row for row in map(json.loads, original.read_text().splitlines())}
        for row in map(json.loads, path.read_text().splitlines()):
            if row['id'] in IDS:
                if row['id'] in frozen:
                    raise ValueError('Duplicate diagnostic ID')
                frozen[row['id']] = row
                originals[row['id']] = values[row['id']]
                sources[row['id']] = {'frozen_file': name, 'original_source': info['source']}
    if set(frozen) != set(IDS):
        raise ValueError('Incomplete diagnostic source coverage')
    payloads = {}
    for arm in ARMS:
        rows = [transform(frozen[key], originals[key], arm) for key in IDS]
        payloads[arm + '.eval.jsonl'] = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    output.mkdir()
    for name, payload in payloads.items():
        (output / name).write_text(payload)
    result = {'version': output.name, 'languages': ['en', 'fr'],
              'source_manifest_sha256': sha(source / 'manifest.json'),
              'generator_sha256': sha(Path(__file__)),
              'reframe_sha256': sha(ROOT / 'training/scripts/build_dialogue_v1.py'),
              'planning_messages_sha256': sha(ROOT / 'src/chat_ai_assistant/planning_messages.py'),
              'count_per_arm': len(IDS), 'arms': list(ARMS), 'source_cases': sources,
              'files': {name: sha(output / name) for name in payloads},
              'status': 'PREPARED; no inference or training',
              'policy': 'Known regressions and controls, not independent acceptance. No labels enter prompts. Only user history presentation varies; tools, system context, current request, permissions and targets stay exact. Current-only is diagnostic removal, not a production memory policy. Genuine history is unchanged by long_greeting. Original frozen results remain unchanged.'}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    print(json.dumps(prepare(), indent=2))
