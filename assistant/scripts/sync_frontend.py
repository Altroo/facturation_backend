"""Copy or verify the canonical MUI UI; application handlers and secrets are excluded."""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'frontend' / 'chat-ai'
FILES = ('ChatAIInterface.tsx', 'ChatAIComposer.tsx', 'ChatAIShortcuts.tsx', 'ChatAIIcons.tsx', 'chat-ai.module.css')
APPS = ('facturation', 'management_projet', 'design_workflow', 'contracts', 'gestion_magasin', 'reservation')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frontends', nargs='+', type=Path)
    parser.add_argument('--write', action='store_true', help='Copy reviewed source; default is verification only.')
    args = parser.parse_args()
    contents = {name: (SOURCE / name).read_bytes() for name in FILES}
    if any(b'lucide-react' in content for content in contents.values()):
        parser.error('The shared UI must use the existing MUI stack only.')
    manifest = {'component': 'Chat AI Assistant', 'version': '1.0.0', 'files': {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}}
    contents['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    failures = []
    for root in args.frontends:
        package = json.loads((root / 'package.json').read_text())
        if package.get('name') not in {app + '_frontend' for app in APPS}:
            parser.error('Target must be an authorized application frontend.')
        if '@mui/material' not in package.get('dependencies', {}):
            parser.error('This adapter requires existing MUI. Do not add a second design framework.')
        target = root / 'src' / 'components' / 'chat-ai' / 'shared'
        if args.write:
            target.mkdir(parents=True, exist_ok=True)
        for name, data in contents.items():
            path = target / name
            if args.write:
                path.write_bytes(data)
            elif not path.is_file() or path.read_bytes() != data:
                failures.append(f'{package["name"]}: {name} differs from canonical UI')
        print(f'{package["name"]}: {"copied" if args.write else "checked"} {len(contents)} UI files')
    if failures:
        raise SystemExit('\n'.join(failures))

if __name__ == '__main__':
    main()
