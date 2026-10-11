"""Exact cumulative scopes for the approved serial application training stages."""

import hashlib
import json
from pathlib import Path

BASE_APPLICATIONS = ('facturation', 'management_projet', 'design_workflow')
STAGES = ('contrat', 'gestion_magasin', 'reservation')


def validate_stage(stage, manifest, train, valid, *, complete_epochs, balanced_applications=False):
    """Reject skipped stages or lost curricula before loading model weights."""
    if stage not in STAGES:
        raise ValueError('Unexpected serial application stage.')
    if type(complete_epochs) is not int or complete_epochs < 1 or balanced_applications:
        raise ValueError('Serial stages require complete positive epochs without oversampling.')
    expected = set(BASE_APPLICATIONS + STAGES[:STAGES.index(stage) + 1])
    applications = manifest.get('applications')
    if (not isinstance(applications, list) or
            not all(isinstance(app, str) for app in applications) or
            len(applications) != len(set(applications)) or set(applications) != expected):
        raise ValueError('Serial stage must retain exactly its approved cumulative applications.')
    if manifest.get('languages') not in (['en', 'fr'], ['fr', 'en']):
        raise ValueError('Serial training requires English and French only.')
    for split in (train, valid):
        if not split or any(not isinstance(row, dict) or row.get('application') not in expected for row in split):
            raise ValueError('Missing or unexpected application metadata in a serial split.')
        if {row['application'] for row in split} != expected:
            raise ValueError('Every retained application requires training and validation examples.')
    return expected


def validate_retained_curriculum(stage, current_manifest, train_payload, valid_payload, retained_directory):
    """Verify the selected predecessor's manifest and exact retained byte prefixes.

    The launcher must bind retained_directory to the accepted predecessor run's
    recorded dataset hashes. This does not choose or accept a predecessor model.
    """
    if stage not in STAGES:
        raise ValueError('Unexpected serial application stage.')
    directory = Path(retained_directory)
    manifest_payload = (directory / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_payload)
    expected = set(BASE_APPLICATIONS + STAGES[:STAGES.index(stage)])
    applications = manifest.get('applications')
    if (not isinstance(applications, list) or
            not all(isinstance(app, str) for app in applications) or
            len(applications) != len(set(applications)) or set(applications) != expected or
            manifest.get('languages') not in (['en', 'fr'], ['fr', 'en'])):
        raise ValueError('Retained dataset must be the preceding cumulative stage in English/French.')
    current_sources = current_manifest.get('sources', {})
    sources = manifest.get('sources')
    if not isinstance(sources, dict) or not sources or any(current_sources.get(name) != digest for name, digest in sources.items()):
        raise ValueError('Preceding application source hashes must be retained.')
    hashes = {}
    for name, current_payload in [('train.jsonl', train_payload), ('valid.jsonl', valid_payload)]:
        payload = (directory / name).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if not payload or not payload.endswith(b'\n') or digest != manifest.get('files', {}).get(name):
            raise ValueError('Retained dataset does not match its validated manifest.')
        if not current_payload.startswith(payload):
            raise ValueError('Current stage must retain every preceding training and validation row byte-for-byte.')
        rows = [json.loads(line) for line in payload.splitlines()]
        if any(not isinstance(row, dict) or row.get('application') not in expected for row in rows):
            raise ValueError('Invalid retained application metadata.')
        if {row['application'] for row in rows} != expected:
            raise ValueError('Retained split is missing a preceding application.')
        hashes[name] = digest
    return {'manifest_sha256': hashlib.sha256(manifest_payload).hexdigest(), 'files': hashes}
