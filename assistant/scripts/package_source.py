"""Curate reviewable assistant source; dry-run unless --write is explicit.

Only backend/assistant is managed. Model artifacts, credentials, local environments,
private test fixtures and generated runtime binaries are never snapshot inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

MARKER = "chat-ai-assistant-source-snapshot"
MANIFEST = "SOURCE_MANIFEST.json"
COLIBRI_REVISION_HINT = "4a4f7a73"
BLOCKED_PARTS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "build", "dist", "models", "adapters", "checkpoints",
    "logs", "private", "testprivate", "test_private", "fixtures",
}
RUNTIME_SUFFIXES = {
    ".c", ".h", ".cpp", ".cu", ".mm", ".inc", ".py", ".sh", ".ps1",
    ".bat", ".cmd", ".comp", ".jinja", ".patch", ".mjs", ".def", ".md", ".txt",
}
PUBLIC_DOCUMENTATION_EXAMPLES = {"AKIAIOSFODNN7EXAMPLE"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"),
    "GitHub credential": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "Hugging Face credential": re.compile(r"\bhf_[A-Za-z0-9]{25,}\b"),
    "API credential": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "credential URL": re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/@\s]+@", re.I),
}
SNAPSHOT_GUIDE = """# Versioned Chat AI Assistant source

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
"""


def allowed(relative: Path) -> bool:
    parts = relative.parts
    if any(part in BLOCKED_PARTS or part.startswith((".venv", "venv", ".env"))
           or part.endswith(".egg-info") for part in parts):
        return False
    if any(part.startswith(".") for part in parts):
        return False
    name, suffix = relative.name, relative.suffix.lower()
    if relative.as_posix() in {"README.md", "pyproject.toml"}:
        return True
    if parts[:2] == ("src", "chat_ai_assistant"):
        return suffix == ".py"
    if parts[:1] == ("scripts",):
        return suffix in {".py", ".sh"}
    if parts[:2] == ("training", "scripts"):
        return suffix in {".py", ".sh"}
    if parts[:2] == ("training", "configs"):
        return suffix in {".lock", ".json", ".yaml", ".yml", ".toml", ".txt"}
    if parts[:2] == ("training", "reports"):
        # Only explicitly curated synthetic evaluation/provenance evidence.
        # Raw evaluation directories and logs remain excluded.
        return suffix in {".json", ".jsonl"}
    if parts[:2] == ("training", "datasets"):
        return suffix in {".json", ".jsonl", ".md"}
    if parts[:1] == ("docs",):
        return suffix in {".md", ".json"}
    if parts[:1] == ("knowledge",):
        return suffix in {".json", ".md"}
    if parts[:1] == ("deploy",):
        return (suffix in {".yaml", ".yml", ".sh", ".post-receive"}
                or name.startswith("Dockerfile") or name == "example.env")
    if parts[:2] == ("runtime", "colibri"):
        if len(parts) < 3:
            return False
        if len(parts) == 3:
            return name in {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"}
        if parts[2] != "c":
            return False
        # Only actual build/runtime source roots, never tiny checkpoints or tests.
        if len(parts) > 4 and parts[3] not in {"tools", "scripts", "shaders"}:
            return False
        return suffix in RUNTIME_SUFFIXES or name == "coli" or name.startswith("Makefile")
    return False


def metadata(data: bytes, mode: int) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "mode": mode}


def digest(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def collect(root: Path) -> tuple[dict, dict]:
    root = root.resolve()
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not allowed(relative) or path.is_dir():
            continue
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Unsafe source path: {relative}")
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"Source changed during snapshot: {relative}")
        if b"\0" in data:
            raise ValueError(f"Binary input rejected: {relative}")
        content = data.decode("utf-8")
        for label, pattern in SECRET_PATTERNS.items():
            if any(match.group() not in PUBLIC_DOCUMENTATION_EXAMPLES
                   for match in pattern.finditer(content)):
                raise ValueError(f"Potential {label}; review source: {relative}")
        mode = 0o755 if path.name == "coli" or path.suffix in {".sh", ".post-receive"} else 0o644
        files[relative.as_posix()] = (data, mode)
    required = {
        "README.md", "pyproject.toml", "src/chat_ai_assistant/__init__.py",
        "scripts/package_source.py", "scripts/package_core.py",
        "training/scripts/train_cpu.py", "training/configs/server-requirements.lock",
        "deploy/Dockerfile.colibri", "deploy/compose.assistant.yml",
        "runtime/colibri/c/Makefile", "runtime/colibri/c/coli",
        "runtime/colibri/c/qwen36.c", "runtime/colibri/LICENSE",
        "runtime/colibri/NOTICE", "runtime/colibri/THIRD_PARTY_NOTICES.md",
    }
    missing = sorted(required - files.keys())
    if missing:
        raise ValueError("Required sources missing: " + ", ".join(missing))
    files["SNAPSHOT.md"] = (SNAPSHOT_GUIDE.encode(), 0o644)
    entries = {name: metadata(*value) for name, value in sorted(files.items())}
    runtime = {name: value for name, value in entries.items() if name.startswith("runtime/colibri/")}
    manifest = {
        "format_version": 1, "managed_by": MARKER,
        "tree_sha256": digest(entries), "files": entries,
        "colibri": {
            "revision_hint": COLIBRI_REVISION_HINT,
            "revision_verified_from_git": False,
            "tree_sha256": digest(runtime),
            "source_identity": "Exact included file hashes; historical revision hint only.",
        },
    }
    return files, manifest


def verify_existing(destination: Path) -> dict:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Snapshot destination must be a real directory.")
    manifest_path = destination / MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Refusing to replace an unrecognized snapshot directory.")
    stored = json.loads(manifest_path.read_text())
    if not isinstance(stored, dict) or stored.get("managed_by") != MARKER or stored.get("format_version") != 1:
        raise ValueError("Unrecognized snapshot manifest.")
    actual = {}
    for path in sorted(destination.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Snapshot contains a symlink: {path.relative_to(destination)}")
        if path.is_dir():
            continue
        # Importing the snapshot may produce Python bytecode. It is neither
        # versioned source nor an operator edit; symlinks are still rejected above.
        if path.suffix == '.pyc' and '__pycache__' in path.relative_to(destination).parts:
            continue
        name = path.relative_to(destination).as_posix()
        if name != MANIFEST:
            actual[name] = metadata(path.read_bytes(), path.stat().st_mode & 0o777)
    runtime = {name: value for name, value in actual.items() if name.startswith("runtime/colibri/")}
    expected_colibri = {
        "revision_hint": COLIBRI_REVISION_HINT,
        "revision_verified_from_git": False,
        "tree_sha256": digest(runtime),
        "source_identity": "Exact included file hashes; historical revision hint only.",
    }
    if (actual != stored.get("files") or digest(actual) != stored.get("tree_sha256")
            or stored.get("colibri") != expected_colibri
            or set(stored) != {"format_version", "managed_by", "tree_sha256", "files", "colibri"}):
        raise ValueError("Snapshot was modified; review changes before regenerating.")
    return stored


def publish(destination: Path, files: dict, manifest: dict) -> None:
    if destination.exists() or destination.is_symlink():
        verify_existing(destination)
    with tempfile.TemporaryDirectory(prefix=".assistant-snapshot-", dir=destination.parent) as tmp:
        stage, previous = Path(tmp) / "new", Path(tmp) / "previous"
        stage.mkdir()
        for name, (data, mode) in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        (stage / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (stage / MANIFEST).chmod(0o644)
        verify_existing(stage)
        if destination.exists():
            destination.rename(previous)
        try:
            stage.rename(destination)
        except BaseException:
            if previous.exists():
                previous.rename(destination)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Publish only backend/assistant.")
    mode.add_argument("--check", action="store_true", help="Verify snapshot matches current source.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    backend = args.backend.resolve()
    if not (backend / "manage.py").is_file() or not (backend / "facturation_backend/settings.py").is_file():
        raise ValueError("Expected the actual Facturation backend checkout.")
    destination = backend / "assistant"
    files, manifest = collect(root)
    if args.write:
        if destination.resolve() == root:
            raise ValueError("Do not overwrite the canonical source directory.")
        publish(destination, files, manifest)
    elif args.check:
        stored = verify_existing(destination)
        if stored != manifest:
            raise ValueError("Snapshot differs from current canonical source; regenerate after review.")
    print(json.dumps({
        "mode": "write" if args.write else "check" if args.check else "dry-run",
        "destination": str(destination), "file_count": len(files),
        "size_bytes": sum(len(data) for data, _ in files.values()),
        "tree_sha256": manifest["tree_sha256"],
        "colibri_tree_sha256": manifest["colibri"]["tree_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"Snapshot refused: {exc}", file=sys.stderr)
        raise SystemExit(1)
