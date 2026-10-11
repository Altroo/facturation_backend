"""Compare a completed candidate with the measured, frozen dialogue baseline.

Read-only analysis of private evaluation evidence. No inference, training,
business tool, model promotion or production activation is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from model_acceptance import assess, FROZEN_EVALUATOR_SHA256

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(path):
    values = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if any(set(value) != {'case'} for value in values):
        raise ValueError('Unexpected evaluation event contract')
    return [value['case'] for value in values]


def application(row):
    context = row.get('trusted_context')
    if context is None:
        context = json.loads(row['messages'][0]['content'].split('Trusted context: ', 1)[1])
    return context['application']


def checked_set(snapshot_path, expected_hash, summary_path, events_path, *, model_id):
    if sha(snapshot_path) != expected_hash:
        raise ValueError('Frozen input changed')
    snapshot = [json.loads(line) for line in snapshot_path.read_text().splitlines()]
    summary = read(summary_path)
    expected = {'dataset_sha256': expected_hash, 'evaluator_sha256': FROZEN_EVALUATOR_SHA256,
                'model_id': model_id, 'max_output_tokens': 512, 'thinking': False, 'mode': 'native'}
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError('Candidate summary is not bound to the pinned evaluation configuration')
    if summary.get('metrics', {}).get('count') != len(snapshot):
        raise ValueError('Incomplete candidate evaluation')
    events = cases(events_path)
    report = assess(snapshot, events)
    return snapshot, events, report


def grouped(snapshot, events):
    by_id = {row['id']: row for row in events}
    return {app: assess(subset, [by_id[row['id']] for row in subset])
            for app in sorted({application(row) for row in snapshot})
            for subset in [[row for row in snapshot if application(row) == app]]}


def checked_process(attestation, process, model_id):
    expected = {'model_id': model_id, 'ctx': 8192, 'max_tokens': 512, 'thinking': False}
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise ValueError('Candidate attestation has another inference configuration')
    if type(process.get('pid')) is not int or process['pid'] <= 0:
        raise ValueError('Invalid candidate process identity')
    cmd = process.get('cmd', [])
    if cmd and cmd[-1] == '':
        cmd = cmd[:-1]  # /proc cmdline ends with a NUL byte.
    runtime = str(Path(attestation['runtime_path']) / 'c/coli')
    if len(cmd) < 3 or Path(cmd[0]).name != 'python3' or cmd[1:3] != [runtime, 'serve']:
        raise ValueError('Candidate process is not the attested Colibri runtime')
    expected_options = ['--model', attestation['model_path'], '--no-tune-profile',
        '--ctx', '8192', '--gpu', 'none', '--ngen', '512', '--no-think', '--temp', '0',
        '--host', '127.0.0.1', '--port']
    remaining = cmd[3:]
    if remaining[:len(expected_options)] != expected_options:
        raise ValueError('Candidate process does not match attested model and configuration')
    tail = remaining[len(expected_options):]
    if (not tail or not tail[0].isdigit() or not 1 <= int(tail[0]) <= 65535 or
            tail[1:] != ['--model-id', model_id, '--max-queue', '2', '--queue-timeout', '10', '--kv-slots', '1']):
        raise ValueError('Unexpected candidate serving configuration')


def build(data, candidate, baseline, baseline_report, evaluation_root, driver_proof):
    manifest_path = data / 'manifest.json'
    manifest = read(manifest_path)
    completed = read(candidate / 'evaluation-complete.json')
    if completed['manifest_sha256'] != sha(manifest_path):
        raise ValueError('Candidate completion belongs to another frozen manifest')
    expected_files = {data.name + '/' + name for name in manifest['inputs']}
    if set(completed['sets']) != expected_files or len(set(completed['sets'].values())) != len(expected_files):
        raise ValueError('Candidate does not cover each frozen set exactly once')
    old_proof = read(baseline / 'baseline-complete.json')
    if old_proof['provider_sha256'] != completed['provider_sha256']:
        raise ValueError('Provider changed between baseline and candidate')
    pinned_driver = read(driver_proof)
    if (completed.get('driver_sha256') != pinned_driver.get('driver_sha256') or
            not completed.get('driver_sha256') or
            pinned_driver.get('provider_sha256') != old_proof['provider_sha256'] or
            pinned_driver.get('model') != old_proof['model'] or
            pinned_driver.get('evaluator_sha256') != FROZEN_EVALUATOR_SHA256):
        raise ValueError('Evaluation driver is not bound to the baseline evidence')
    old = read(baseline_report)
    if old['manifest_sha256'] != sha(manifest_path) or old['model_id'] != old_proof['model']:
        raise ValueError('Baseline belongs to another model or manifest')
    if sha(baseline_report) != read(baseline / 'baseline-report.json')['report_sha256']:
        raise ValueError('Recorded baseline report changed')
    attestation = read(candidate / 'inference-attestation.json')
    after = read(candidate / 'inference-post-evaluation-attestation.json')
    if attestation != after:
        raise ValueError('Candidate identity, configuration or artifacts changed across evaluation')
    process = read(candidate / 'candidate-process-before.json')
    if process != read(candidate / 'candidate-process-after.json'):
        raise ValueError('Candidate process changed across evaluation')
    checked_process(attestation, process, completed['model_id'])
    snapshots, events, sets = [], [], []
    for name in manifest['inputs']:
        relative = data.name + '/' + name
        label = completed['sets'][relative]
        if Path(label).name != label:
            raise ValueError('Invalid private evaluation label')
        folder = evaluation_root / label
        rows, actual, result = checked_set(data / name, manifest['files'][name], folder / 'summary.json',
            folder / 'events.jsonl', model_id=completed['model_id'])
        snapshots.extend(rows); events.extend(actual)
        sets.append({'dataset': name, 'dataset_sha256': sha(data / name),
                     'events_sha256': sha(folder / 'events.jsonl'), 'assessment': result})
    if completed['count'] != len(snapshots):
        raise ValueError('Candidate completion count does not match frozen cases')
    previous = cases(baseline / 'combined-events.jsonl')
    before_report = assess(snapshots, previous)
    if before_report != old['reframed']:
        raise ValueError('Baseline events no longer reproduce the published assessment')
    current = assess(snapshots, events)
    by_app = grouped(snapshots, events)
    passed = current['model_targets_passed'] and all(item['assessment']['model_targets_passed'] for item in sets)
    return {'version': manifest['version'], 'baseline_model_id': old['model_id'],
        'candidate_model_id': completed['model_id'], 'manifest_sha256': sha(manifest_path),
        'frozen_evaluator_sha256': FROZEN_EVALUATOR_SHA256,
        'acceptance_script_sha256': sha(Path(__file__).with_name('model_acceptance.py')),
        'report_script_sha256': sha(Path(__file__)),
        'baseline_report_sha256': sha(baseline_report),
        'candidate_completion_sha256': sha(candidate / 'evaluation-complete.json'),
        'candidate_artifact_digests': {name: value['sha256'] for name,value in attestation['artifacts'].items()},
        'driver_sha256': completed['driver_sha256'], 'driver_proof_sha256': sha(driver_proof),
        'provider_sha256': completed['provider_sha256'], 'baseline': before_report,
        'candidate': current, 'baseline_by_application': grouped(snapshots, previous),
        'candidate_by_application': by_app, 'sets': sets,
        'all_frozen_sets_passed': passed,
        'native_backend_security_verified': None, 'production_activation': 'NOT AUTHORIZED BY THIS REPORT',
        'limitations': ['Every candidate case is freshly measured; the baseline reuses 360 identical inputs and measures 78 changed histories separately.',
            'No latency comparison is inferred from the combined baseline.',
            'Synthetic bilingual cases and regression sets are not blind external certification.',
            'Knowledge query scoring does not measure retrieval factuality. Native security and real application tests remain separate.',
            'Passing aggregate scores alone is insufficient: each frozen set must pass the existing acceptance gates.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('data','candidate','baseline','baseline-report','evaluation-root','driver-proof','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if sha(ROOT/'training/scripts/evaluate_snapshot.py') != FROZEN_EVALUATOR_SHA256:
        raise ValueError('Frozen evaluator changed')
    report=build(args.data.resolve(),args.candidate,args.baseline,args.baseline_report,args.evaluation_root,args.driver_proof)
    with args.output.open('x') as handle:
        json.dump(report,handle,indent=2,ensure_ascii=False);handle.write('\n')
    print(json.dumps({'candidate':report['candidate']['metrics'],'all_frozen_sets_passed':report['all_frozen_sets_passed']}))


if __name__=='__main__':
    main()
