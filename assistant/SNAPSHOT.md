# Versioned Chat AI Assistant source

This directory is a generated, reviewable source snapshot. The canonical working
copy remains the central Chat AI Assistant directory. Do not edit this snapshot:
edit canonical source, review changes, then regenerate.

From the canonical directory:

```sh
python3 scripts/package_source.py --backend /path/to/facturation_backend
python3 scripts/package_source.py --backend /path/to/facturation_backend --write
python3 scripts/package_source.py --backend /path/to/facturation_backend --check
python3 scripts/package_core.py --backend /path/to/facturation_backend
```

The first command is read-only. `--write` replaces only this generated directory,
and refuses a modified/unrecognized existing snapshot. `--check` verifies all
snapshot contents and compares them with current canonical inputs. Re-run both
packagers after final model datasets, documentation and source changes; review the
Git diff before release. Rebuilding the wheel does not regenerate this snapshot.

`SOURCE_MANIFEST.json` records each file's SHA256, byte size and executable mode.
Its tree digests pin exact source content. Colibri's historical revision hint is
`4a4f7a73`; no Git metadata exists in the working runtime, so the hint is not an
independently verified commit identity. Included source hashes are authoritative.
Colibri LICENSE, NOTICE and THIRD_PARTY_NOTICES.md are preserved.

Included: reusable Python source, project metadata, approved knowledge, docs,
deployment drafts, packaging/training scripts, dependency configuration and
synthetic training datasets, explicitly curated JSON/JSONL evidence from
training/reports, plus Colibri C/Python/build sources.

Excluded: model weights/tokenizers, adapters/checkpoints, environments, credentials,
logs, caches, compiled binaries, runtime test fixtures/tiny models/profiles and
private test artifacts. Raw training/evaluations directories remain excluded.
Only separately reviewed synthetic cases, measurements and provenance belong in
training/reports; never put browser/API/private-payload logs there. The existing
secret checks apply to reports too. No production data is extracted.

The snapshot does not install hooks, deploy services, publish remotes, train or
activate a model. See docs/AI_DEPLOYMENT.md and the live implementation status.
