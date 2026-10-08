"""Fingerprint a locally served Colibri artifact for reproducible evaluation."""
import argparse
import hashlib
import json
import platform
from pathlib import Path


def fingerprint(root, files):
    entries = {}
    for file in sorted(files):
        digest = hashlib.sha256()
        before = file.stat()
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        after = file.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Artifact changed while hashing: ' + file.name)
        entries[file.relative_to(root).as_posix()] = {'sha256': digest.hexdigest(), 'size_bytes': after.st_size}
    if not entries:
        raise ValueError('No artifacts found.')
    canonical = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return {'sha256': hashlib.sha256(canonical).hexdigest(), 'files': entries}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--service-unit', required=True)
    parser.add_argument('--model-id', default='chat-ai-facturation')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to replace an inference attestation.')
    weights = fingerprint(args.model, args.model.glob('*.safetensors'))
    tokenizer = fingerprint(args.model, [args.model / name for name in ('tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja')])
    config = fingerprint(args.model, [args.model / name for name in ('config.json', 'qwen36_meta.json')])
    runtime = fingerprint(args.runtime, [args.runtime / 'c/qwen36', args.runtime / 'c/coli', *sorted((args.runtime / 'c').glob('*.py')), *sorted((args.runtime / 'c/tools').glob('*.py'))])
    report = {'model_id': args.model_id, 'model_path': str(args.model.resolve()),
              'runtime_path': str(args.runtime.resolve()), 'service_unit': args.service_unit,
              'inference_platform': platform.platform(), 'host': platform.node(),
              'ctx': 8192, 'max_tokens': 512, 'thinking': False, 'threads': args.threads,
              'runtime_options': 'Qwen engine; dense int8; GPU none; temperature 0; one KV slot',
              'attestation': 'Artifacts hashed on inference host before evaluation. Operator must verify service argv matches paths and prevent replacements during the run.',
              'artifacts': {'weights': weights, 'tokenizer': tokenizer, 'config': config, 'runtime': runtime}}
    for name in ('weights', 'tokenizer', 'config', 'runtime'):
        report[name + '_sha256'] = report['artifacts'][name]['sha256']
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('model_id', 'weights_sha256', 'runtime_sha256')}))


if __name__ == '__main__':
    main()
