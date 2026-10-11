"""Prepare a small, separately versioned instruction ablation; never train or infer.

Known failures are explicitly regression cases. Newly authored controls share
native synthetic schema/context templates and are not an independent certification.
The original frozen scenarios, labels, capability sets and tool schemas are preserved.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'training/datasets/shared-dialogue-v1-en-fr'
OUTPUT = ROOT / 'training/datasets/planner-rules-v1-en-fr'

NAME_RULE = """Copy lookup names, article/document references and identifiers exactly from the request or authorized context, including accents and spelling. Do not translate these values to match the response language. User-facing explanations follow the current user's language. Canonical status codes and ISO dates still follow the tool schema. Only transform editable prose when the user explicitly requests that transformation; this never grants mutation permission."""
DATE_RULE = """A named full month plus an explicit four-digit year supplies a complete reporting period, even when that year differs from today's year. For supported date filters, use the inclusive first and last calendar dates of that month in ISO format. Ask for a year only when it is missing or ambiguous; never infer it from today or old messages. Do not discard other requested filters or use a tool that does not support the requested operation."""
ARMS = {'original': '', 'names': NAME_RULE, 'dates': DATE_RULE,
        'both': NAME_RULE + '\n' + DATE_RULE}
REGRESSIONS = (
    'design-workflow-v3-en-fr-fresh-assignee-en',
    'design-workflow-v3-en-fr-fresh-time-en',
    'design_workflow-refinement-v1-explicit-date-fr',
    'design_workflow-refinement-v1-explicit-date-en',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(row, arm):
    """Only append generic system instructions; labels never inform the prompt."""
    if arm not in ARMS:
        raise ValueError('Unknown diagnostic arm')
    result = deepcopy(row)
    if len(result['messages']) != 2 or result['messages'][0]['role'] != 'system':
        raise ValueError('Expected a frozen single-current-message envelope')
    if ARMS[arm]:
        # Append after context without parsing/replacing user-controlled content.
        result['messages'][0]['content'] += '\nAdditional argument rules:\n' + ARMS[arm]
    return result


def controls(rows):
    lookup = rows[REGRESSIONS[0]]
    period = rows[REGRESSIONS[3]]
    examples = [
        ('literal-en', lookup, 'en',
         'For Jardin d’Été Démo, find tasks assigned to Démo Zoé.',
         'search_records', {'resource': 'task', 'project_name': 'Jardin d’Été Démo', 'assignee_name': 'Démo Zoé'}),
        ('literal-fr', lookup, 'fr',
         'Pour Blue Courtyard Demo, trouve les tâches assignées à Démo Zoé.',
         'search_records', {'resource': 'task', 'project_name': 'Blue Courtyard Demo', 'assignee_name': 'Démo Zoé'}),
        ('century-en', period, 'en',
         'Show working time for Atelier Synthétique in February 2100.',
         'time_report', {'project_name': 'Atelier Synthétique', 'date_from': '2100-02-01', 'date_to': '2100-02-28'}),
        ('century-fr', period, 'fr',
         'Montre le temps de travail sur Atelier Synthétique en février 2000.',
         'time_report', {'project_name': 'Atelier Synthétique', 'date_from': '2000-02-01', 'date_to': '2000-02-29'}),
        ('missing-en', period, 'en',
         'How much working time for Atelier Synthétique in September?',
         'clarify', {'reason': 'missing_details', 'language': 'en'}),
        ('missing-fr', period, 'fr',
         'Combien de temps de travail sur Atelier Synthétique en septembre ?',
         'clarify', {'reason': 'missing_details', 'language': 'fr'}),
        ('status-en', lookup, 'en',
         'Show tasks in review for Jardin Démo.',
         'search_records', {'resource': 'task', 'project_name': 'Jardin Démo', 'status': 'in_review'}),
        ('status-fr', lookup, 'fr',
         'Montre les tâches en revue sur Jardin Démo.',
         'search_records', {'resource': 'task', 'project_name': 'Jardin Démo', 'status': 'in_review'}),
    ]
    result = []
    for name, template, language, prompt, tool, arguments in examples:
        row = deepcopy(template)
        old_context = json.dumps(row['trusted_context'], ensure_ascii=False)
        row.update(id='planner-rules-control-' + name, category='new_synthetic_control', language=language,
                   expected={'tool': tool, 'arguments': arguments})
        row['trusted_context']['interface_language'] = language
        content = row['messages'][0]['content']
        assert content.endswith(old_context)
        row['messages'][0]['content'] = content[:-len(old_context)] + json.dumps(row['trusted_context'], ensure_ascii=False)
        row['messages'][1]['content'] = prompt
        result.append(row)
    return result


def prepare(source=SOURCE, output=OUTPUT):
    if output.exists():
        raise ValueError('Never overwrite a versioned diagnostic')
    manifest = json.loads((source / 'manifest.json').read_text())
    rows = {}
    for name in manifest['inputs']:
        path = source / name
        if sha(path) != manifest['files'][name]:
            raise ValueError('Frozen source hash changed')
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row['id'] in rows:
                raise ValueError('Duplicate frozen ID')
            rows[row['id']] = row
    selected = [deepcopy(rows[key]) for key in REGRESSIONS] + controls(rows)
    from jsonschema import Draft202012Validator
    for row in selected:
        schemas = {tool['function']['name']: tool['function']['parameters'] for tool in row['offered_tool_schemas']}
        if row['expected']['tool'] != 'clarify':
            Draft202012Validator(schemas[row['expected']['tool']]).validate(row['expected']['arguments'])
    payloads = {arm + '.eval.jsonl': ''.join(json.dumps(transform(row, arm), ensure_ascii=False) + '\n' for row in selected)
                for arm in ARMS}
    output.mkdir()
    for name, payload in payloads.items():
        (output / name).write_text(payload)
    evidence = {'version': output.name, 'source_manifest_sha256': sha(source / 'manifest.json'),
                'generator_sha256': sha(Path(__file__)), 'count_per_arm': len(selected),
                'regression_ids': list(REGRESSIONS), 'new_control_ids': [row['id'] for row in selected[4:]],
                'arms': ARMS, 'files': {name: sha(output / name) for name in payloads},
                'status': 'PREPARED; not measured or trained',
                'policy': 'Instruction-only ablation. No expected target is inserted into prompts. Same tools, permissions, native contexts and original labels per arm. Known failures are regressions; new synthetic controls are not independent certification. Does not replace the full frozen evaluation or authorize deployment.'}
    (output / 'manifest.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    print(json.dumps(prepare(), indent=2))
