"""Build the shared core wheel into a Facturation backend checkout, with checksum."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--backend',type=Path,required=True);a=p.parse_args()
if not (a.backend/'manage.py').is_file():raise SystemExit('Expected the actual Facturation backend checkout.')
out=a.backend/'vendor';out.mkdir(exist_ok=True)
subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-build-isolation',str(root),'--wheel-dir',str(out)],check=True)
wheel=out/'chat_ai_assistant-0.1.0-py3-none-any.whl'
manifest={'file':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
          'source_files':{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((root/'src').rglob('*.py'))}}
(out/'chat-ai-core-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'wheel':str(wheel),'sha256':manifest['sha256']}))
