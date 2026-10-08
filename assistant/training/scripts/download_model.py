"""Download a public, revision-pinned checkpoint into the isolated training directory."""
from huggingface_hub import snapshot_download
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
repo='Qwen/Qwen3.5-0.8B';revision='2fc06364715b967f1860aea9cf38778875588b17'
path=snapshot_download(repo,revision=revision,local_dir=root/'models/Qwen3.5-0.8B',allow_patterns=['*.json','*.jinja','*.safetensors','LICENSE'],max_workers=2,token=False)
(root/'evaluations/download-manifest.json').write_text(json.dumps({'repository':repo,'revision':revision,'path':path,'purpose':'server-only synthetic LoRA training; no service activation'},indent=2))
print('Pinned model downloaded for isolated training.',flush=True)
