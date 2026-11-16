"""Install pinned public translation models during setup, never during a PDF request."""

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def prepare_models(directory, *, archives=None, check=False, manifest_path=None):
    manifest_path = Path(manifest_path or Path(__file__).with_name("translation_models.json"))
    packages = json.loads(manifest_path.read_text())
    root = Path(directory)
    if not check:
        root.mkdir(parents=True, exist_ok=True)
    results = []
    for package in packages:
        pair = package["pair"]
        target = root / pair
        marker = target / "package-source.json"
        required = (target / "model/model.bin", target / "sentencepiece.model", target / "metadata.json")
        if marker.is_file() and all(path.is_file() for path in required):
            installed = json.loads(marker.read_text())
            if installed.get("sha256") == package["sha256"]:
                results.append({"pair": pair, "status": "ready"})
                continue
        if check:
            raise ValueError(f"Missing or incomplete offline translation model: {pair}")
        if target.exists():
            raise ValueError(f"Model directory already exists without valid provenance: {pair}")
        with tempfile.TemporaryDirectory(prefix=f".install-{pair}-", dir=root) as temporary:
            temporary = Path(temporary)
            archive = Path(archives) / f"{pair}.argosmodel" if archives else temporary / "model.argosmodel"
            if not archives:
                subprocess.run([
                    "curl", "--fail", "--silent", "--show-error", "--location",
                    "--retry", "3", "--retry-all-errors", "--max-time", "600",
                    "--output", str(archive), package["url"],
                ], check=True)
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != package["sha256"]:
                raise ValueError(f"Translation model checksum mismatch: {pair}")
            staged = temporary / "extracted"
            staged.mkdir()
            with ZipFile(archive) as contents:
                names = contents.namelist()
                metadata_name = next(name for name in names if len(PurePosixPath(name).parts) == 2 and name.endswith("/metadata.json"))
                metadata = json.loads(contents.read(metadata_name))
                if f"{metadata['from_code']}_{metadata['to_code']}" != pair or metadata["package_version"] != package["version"]:
                    raise ValueError(f"Translation model metadata mismatch: {pair}")
                prefix = PurePosixPath(metadata_name).parts[0]
                for item in contents.infolist():
                    path = PurePosixPath(item.filename)
                    if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(item.external_attr >> 16):
                        raise ValueError("Unsafe path in translation model package")
                    if not path.parts or path.parts[0] != prefix:
                        raise ValueError("Unexpected translation model package root")
                    relative = Path(*path.parts[1:])
                    if not relative.parts or (relative.parts[0] != "model" and relative.name not in ("metadata.json", "sentencepiece.model", "README.md", "LICENSE")):
                        continue
                    destination = staged / relative
                    if item.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with contents.open(item) as source, destination.open("wb") as output:
                            shutil.copyfileobj(source, output)
            if not all((staged / name).is_file() for name in ("model/model.bin", "sentencepiece.model", "metadata.json")):
                raise ValueError(f"Incomplete translation model package: {pair}")
            (staged / "package-source.json").write_text(json.dumps(package, indent=2) + "\n")
            for path in staged.rglob("*"):
                path.chmod(0o755 if path.is_dir() else 0o644)
            staged.chmod(0o755)
            staged.rename(target)
            results.append({"pair": pair, "status": "installed"})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--archives")
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    print(json.dumps(prepare_models(options.directory, archives=options.archives, check=options.check)))
