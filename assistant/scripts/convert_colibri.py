#!/usr/bin/env python3
"""Prepare tied embeddings losslessly, then run the pinned Colibri converter."""
import argparse,json,subprocess,sys
from pathlib import Path
from safetensors import safe_open
from safetensors.torch import save_file

p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--runtime',type=Path,default=Path(__file__).resolve().parents[1]/'runtime/colibri');a=p.parse_args()
source=a.source.resolve();cfg=json.loads((source/'config.json').read_text());text=cfg.get('text_config',cfg)
index=json.loads((source/'model.safetensors.index.json').read_text());wm=index['weight_map']
if text.get('tie_word_embeddings') and not any(k.endswith('lm_head.weight') for k in wm):
    normalized=source.with_name(source.name+'-tied-export');normalized.mkdir(exist_ok=True)
    for file in source.iterdir():
        if file.is_file() and file.name!='model.safetensors.index.json':
            target=normalized/file.name
            if not target.exists():target.symlink_to(file)
    key=next(k for k in wm if k.endswith('embed_tokens.weight'))
    with safe_open(str(source/wm[key]),framework='pt') as f:weight=f.get_tensor(key)
    save_file({'lm_head.weight':weight.clone()},str(normalized/'tied-lm-head.safetensors'))
    wm['lm_head.weight']='tied-lm-head.safetensors'
    (normalized/'model.safetensors.index.json').write_text(json.dumps(index))
    source=normalized
subprocess.run([sys.executable,str(a.runtime/'c/tools/convert_qwen36.py'),'--model',str(source),'--out',str(a.output),'--ebits','8'],check=True)

# Exported weights contain only the model artifact. Make them readable by the
# dedicated non-root inference UID when mounted read-only into its container.
a.output.chmod(0o755)
for artifact in a.output.iterdir():
    if artifact.is_file() and not artifact.is_symlink():
        artifact.chmod(0o644)
