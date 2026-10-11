"""Build the shared core wheel into an approved Django backend checkout, with checksum."""
import argparse, hashlib, json, subprocess, sys, tomllib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--backend',type=Path,required=True);a=p.parse_args()
if not (a.backend/'manage.py').is_file():raise SystemExit('Expected an actual Django backend checkout.')
out=a.backend/'vendor';out.mkdir(exist_ok=True)
subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation',str(root),'--wheel-dir',str(out)],check=True)
version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
wheel=out/f'chat_ai_assistant-{version}-py3-none-any.whl'
manifest={'version':version,'file':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
          'source_files':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((root/'src').rglob('*.py'))}}
(out/'chat-ai-core-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'wheel':str(wheel),'sha256':manifest['sha256']}))
