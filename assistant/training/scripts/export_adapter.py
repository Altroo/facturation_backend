"""Merge the trained adapter into a separate checkpoint; never activate it."""
import argparse, json, platform
from pathlib import Path
import torch
from peft import PeftModel
from transformers import AutoTokenizer,Qwen3_5ForConditionalGeneration
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--adapter',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if platform.system()!='Linux':raise SystemExit('Export this server-trained artifact on the approved Linux server.')
if a.output.exists():raise SystemExit('Refusing to overwrite an existing model export.')
torch.set_num_threads(14)
model=Qwen3_5ForConditionalGeneration.from_pretrained(a.base,local_files_only=True,dtype=torch.float32)
model=PeftModel.from_pretrained(model,a.adapter,local_files_only=True)
model=model.merge_and_unload(safe_merge=True)
model.save_pretrained(a.output,max_shard_size='1GB');AutoTokenizer.from_pretrained(a.base,local_files_only=True).save_pretrained(a.output)
(a.output/'chat_ai_export.json').write_text(json.dumps({'base':a.base,'adapter':a.adapter,'format':'HF float32 merged for subsequent Colibri conversion','deployment':'not deployed'},indent=2))
print('Server adapter exported without activating a service.',flush=True)
