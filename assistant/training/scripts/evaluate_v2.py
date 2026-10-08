"""Versioned model-only evaluation; never executes application tools.

--model-manifest requires an operator-attested JSON object with model_id,
weights_sha256, tokenizer_sha256, config_sha256, runtime_sha256, and
inference_platform. Hashes identify file contents, or canonical per-file hash
manifests for multi-file artifacts. Include runtime options and hardware details
as extra fields when relevant. The entire manifest is frozen into run identity.
This client cannot verify which weights a remote endpoint actually loaded.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from chat_ai_assistant.provider import ChatAIModelService, ModelConfig
from chat_ai_assistant.contracts import ChatAITool, ChatAIToolRegistry
from chat_ai_assistant.clarifications import MESSAGES


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model_manifest(path):
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError('Model manifest exceeds 1 MiB.')
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError('Model manifest must describe one inference model as an object.')
    for key in ('model_id', 'inference_platform'):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f'Model manifest requires a nonempty {key}.')
    for key in ('weights_sha256', 'tokenizer_sha256', 'config_sha256', 'runtime_sha256'):
        value = manifest.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError(f'Model manifest requires a lowercase SHA-256 in {key}.')
    return manifest, hashlib.sha256(raw).hexdigest()


def run_identity(args, manifest, manifest_sha256):
    return {'dataset_sha256': digest(args.dataset), 'schemas_sha256': digest(args.schemas),
            'provider_sha256': digest(ROOT / 'src/chat_ai_assistant/provider.py'),
            'evaluator_sha256': digest(Path(__file__)), 'thinking': args.thinking,
            'max_tokens': args.max_tokens, 'timeout_seconds': args.timeout,
            'client_platform': platform.platform(), 'client_python': platform.python_version(),
            'inference_platform': manifest['inference_platform'],
            'model_manifest_sha256': manifest_sha256, 'model_manifest': manifest,
            'url': args.url, 'argument_scoring_version': 'v2.1-fixed-knowledge-denominator'}


def offered_tools(row, registry):
    """Replay the frozen production capability-filtered schemas, not just names."""
    names = row.get('offered_tools', list(registry.tools))
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise ValueError('Invalid or duplicate offered tool names.')
    tools = [registry.get(name) for name in names]
    frozen = row.get('offered_tool_schemas')
    if frozen is None:
        return tools
    if not isinstance(frozen, list) or len(frozen) != len(names):
        raise ValueError('Frozen schemas must cover every offered tool exactly once.')
    by_name = {}
    for item in frozen:
        if not isinstance(item, dict) or item.get('type') != 'function':
            raise ValueError('Invalid frozen function schema.')
        function = item.get('function', {})
        name = function.get('name')
        if name not in names or name in by_name:
            raise ValueError('Unexpected or duplicate frozen function schema.')
        by_name[name] = function
    scoped = [replace(tool, description=by_name[tool.name]['description'],
                      input_schema=by_name[tool.name]['parameters']) for tool in tools]
    # Validate the immutable dataset schema before any inference call.
    ChatAIToolRegistry(scoped)
    return scoped


def argument_match(expected, actual, tool):
    if tool == 'knowledge':
        # Search paraphrases require human semantic review, not a nonempty-string pass.
        return None
    if tool == 'clarify':
        for language, reasons in MESSAGES.items():
            for reason, text in reasons.items():
                if actual.get('message') == text:
                    return expected == {'reason': reason, 'language': language}
        return False
    args = dict(actual.get('arguments', {}))
    for key, default in [('limit', 10), ('offset', 0), ('unpaid', False)]:
        if key not in expected and args.get(key) == default:
            args.pop(key)
    return args == expected


class MeasuredModel(ChatAIModelService):
    def stream(self, *args, **kwargs):
        self.first_event = None
        start = time.monotonic()
        for delta in super().stream(*args, **kwargs):
            if self.first_event is None and (delta.get('content') or delta.get('tool_calls')):
                self.first_event = time.monotonic() - start
            yield delta


def percentage(rows, key):
    scored = [row[key] for row in rows if row.get(key) is not None]
    return {'passed': sum(scored), 'scored': len(scored),
            'percent': round(100 * sum(scored) / len(scored), 2) if scored else None}


def summarize(rows):
    return {'count': len(rows), **{key: percentage(rows, key) for key in
            ['tool_correct', 'arguments_correct', 'structured_valid']}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--schemas', type=Path, required=True)
    parser.add_argument('--model-manifest', type=Path, required=True,
                        help='Immutable inference model/runtime attestation; see module docstring.')
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--thinking', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if Path(args.label).name != args.label:
        raise SystemExit('Label must be a single directory name.')
    if args.timeout <= 0 or args.max_tokens <= 0:
        parser.error('Timeout and max-tokens must be positive.')
    try:
        manifest, manifest_sha256 = load_model_manifest(args.model_manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    schemas = json.loads(args.schemas.read_text())
    registry = ChatAIToolRegistry([ChatAITool(
        item['function']['name'], item['function']['description'],
        item['function']['parameters'], {'type': 'object'}, item['function']['name']
    ) for item in schemas])
    inputs = [json.loads(line) for line in args.dataset.read_text().splitlines() if line]
    if any(row.get('language') not in ('en','fr') for row in inputs):
        raise SystemExit('Current evaluation scope is English/French only. Historical runs remain unchanged.')
    if not inputs or len({row['id'] for row in inputs}) != len(inputs):
        raise SystemExit('Empty dataset or duplicate case IDs.')
    identity = run_identity(args, manifest, manifest_sha256)
    output = ROOT / 'training/evaluations' / args.label
    output.mkdir(exist_ok=True)
    identity_path = output / 'run.json'
    if identity_path.exists():
        if not args.resume or json.loads(identity_path.read_text()) != identity:
            raise SystemExit('Existing run: use --resume with identical configuration or a new label.')
    else:
        if (output / 'cases.jsonl').exists():
            raise SystemExit('Unidentified existing cases; choose a new label.')
        identity_path.write_text(json.dumps(identity, indent=2))
    cases_path = output / 'cases.jsonl'
    rows = [json.loads(line) for line in cases_path.read_text().splitlines()] if cases_path.exists() else []
    completed = {row['id'] for row in rows}
    if len(completed) != len(rows) or not completed <= {row['id'] for row in inputs}:
        raise SystemExit('Inconsistent resumed case file.')
    model = MeasuredModel(ModelConfig(args.url, manifest['model_id'], mode='native',
                                     max_tokens=args.max_tokens, thinking=args.thinking,
                                     timeout=args.timeout))
    for row in inputs:
        if row['id'] in completed:
            continue
        result = {key: row[key] for key in ('id', 'category', 'language', 'expected')}
        result.update(tool_correct=False, arguments_correct=None if row['expected']['tool']=='knowledge' else False, structured_valid=False)
        start = time.monotonic()
        model.first_event = None
        try:
            # Frozen per-case tool subset may be supplied by the same production router.
            offered = offered_tools(row, registry)
            action, usage = model.choose(row['messages'], offered)
            result.update(action=action, usage=usage, structured_valid=True)
            result['tool_correct'] = action['tool'] == row['expected']['tool']
            result['arguments_correct'] = (None if row['expected']['tool']=='knowledge' else
                argument_match(row['expected']['arguments'], action, action['tool'])
                if result['tool_correct'] else False)
            if row['expected']['tool']=='knowledge':
                result['arguments_correct']=None
        except Exception as exc:
            result['error'] = getattr(exc, 'code', type(exc).__name__)
        elapsed = time.monotonic() - start
        result['latency_s'] = round(elapsed, 4)
        result['time_to_first_visible_event_s'] = model.first_event
        tokens = result.get('usage', {}).get('completion_tokens', 0)
        result['completion_tokens_per_wall_second'] = round(tokens / elapsed, 3) if tokens else None
        rows.append(result)
        with cases_path.open('a') as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
        print(f"{row['id']} tool={result['tool_correct']} arguments={result['arguments_correct']} seconds={elapsed:.2f}", flush=True)
    times = sorted(row['latency_s'] for row in rows)
    throughput = [row['completion_tokens_per_wall_second'] for row in rows if row['completion_tokens_per_wall_second'] is not None]
    report = {**identity, 'label': args.label, 'metrics': summarize(rows),
              'latency_mean_s': statistics.mean(times), 'latency_p95_s': times[math.ceil(.95*len(times))-1],
              'completion_tokens_per_wall_second_mean': statistics.mean(throughput) if throughput else None,
              'by_language': {name: summarize([row for row in rows if row['language'] == name]) for name in sorted({r['language'] for r in rows})},
              'by_category': {name: summarize([row for row in rows if row['category'] == name]) for name in sorted({r['category'] for r in rows})},
              'failures': [row['id'] for row in rows if not row['tool_correct'] or row['arguments_correct'] is False],
              'limitations': ['Synthetic held-out cases; no business operations executed.',
                'Exact arguments after documented default normalization; knowledge query paraphrases are unscored and need manual review.',
                'Tool calls are buffered by Colibri; visible-event latency is not time to first generated token.',
                'Performance applies only to the attested inference platform and runtime configuration.',
                'Model provenance is operator-attested; this client cannot verify remote loaded weights.']}
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report['metrics'], indent=2))


if __name__ == '__main__':
    main()
