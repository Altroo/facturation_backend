"""Server-only bounded CPU LoRA. Never uses production data or activates an adapter."""
import argparse, hashlib, json, os, platform, random, resource, time
from pathlib import Path
from collections.abc import Mapping
from importlib import metadata


def file_fingerprint(path):
    """Bounded-memory content hashing; fail if an artifact changes while read."""
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'Artifact changed during fingerprinting: {path.name}')
    return {'size_bytes': after.st_size, 'sha256': value.hexdigest()}


def artifact_group(root, paths):
    files = {path.relative_to(root).as_posix(): file_fingerprint(path)
             for path in sorted(set(paths))}
    if not files:
        raise ValueError('Missing model artifacts for fingerprinting.')
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    return {'sha256': hashlib.sha256(canonical).hexdigest(), 'files': files}


def model_fingerprint(root):
    """Hash the weights referenced by the checkpoint and tokenizer/config inputs."""
    weight_paths = []
    for name in ('model.safetensors.index.json', 'pytorch_model.bin.index.json'):
        index = root / name
        if not index.is_file():
            continue
        weight_map = json.loads(index.read_text()).get('weight_map')
        if not isinstance(weight_map, dict) or not weight_map:
            raise ValueError(f'Invalid checkpoint index: {name}')
        weight_paths.append(index)
        for name in set(weight_map.values()):
            if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Invalid checkpoint shard path.')
            weight_paths.append(root / name)
    if not weight_paths:
        weight_paths = list(root.glob('*.safetensors')) + list(root.glob('pytorch_model*.bin'))
    tokenizer_names = ('tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
                       'added_tokens.json', 'merges.txt', 'vocab.json', 'tokenizer.model',
                       'spiece.model', 'chat_template.jinja')
    config_names = ('config.json', 'generation_config.json', 'preprocessor_config.json',
                    'processor_config.json', 'video_preprocessor_config.json')
    if not (root / 'config.json').is_file():
        raise ValueError('Model config.json is required.')
    tokenizer_paths = [root / name for name in tokenizer_names if (root / name).is_file()]
    tokenizer_paths.extend((root / 'chat_templates').glob('*.jinja'))
    return {'weights': artifact_group(root, weight_paths),
            'tokenizer': artifact_group(root, tokenizer_paths),
            'config': artifact_group(root, [root / name for name in config_names if (root / name).is_file()])}


p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=96);p.add_argument('--threads',type=int,default=14);p.add_argument('--max-seq-length',type=int,default=4096);p.add_argument('--learning-rate',type=float,default=0.0001);a=p.parse_args()
if platform.system()!='Linux' or os.environ.get('CHAT_AI_TRAINING_SERVER')!='1':raise SystemExit('Training is restricted to the approved Linux server.')
dataset_manifest=json.loads((a.data/'manifest.json').read_text())
if set(dataset_manifest.get('languages',[]))!={'en','fr'}:raise SystemExit('Current training scope requires an English/French-only dataset manifest.')
import torch
from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
from peft import LoraConfig,get_peft_model
import psutil
if psutil.virtual_memory().available<psutil.virtual_memory().total*.10:raise SystemExit('Insufficient spare memory; training not started.')
if a.steps <= 0 or a.threads <= 0 or a.max_seq_length <= 0 or not 0 < a.learning_rate < float('inf'):
    raise SystemExit('Training steps, threads, context and learning rate must be positive and finite.')
script_fingerprint = file_fingerprint(Path(__file__))
base_fingerprint = model_fingerprint(a.model)
package_versions = dict(sorted((distribution.metadata['Name'], distribution.version)
                               for distribution in metadata.distributions() if distribution.metadata['Name']))
train_bytes = (a.data / 'train.jsonl').read_bytes()
validation_bytes = (a.data / 'valid.jsonl').read_bytes()
torch.set_num_threads(a.threads);torch.set_num_interop_threads(1);torch.manual_seed(17);random.seed(17)
a.output.mkdir(parents=True,exist_ok=False)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
model=Qwen3_5ForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,attn_implementation='eager')
model.config.use_cache=False
layers=model.config.text_config.num_hidden_layers
# Last four layers only; leave most of the base frozen and omit vision inputs entirely.
regex=r'.*language_model\.layers\.('+ '|'.join(str(i) for i in range(layers-4,layers)) +r')\.(mlp\.(up_proj|down_proj)|self_attn\.(q_proj|v_proj)|linear_attn\.(in_proj_qkv|out_proj))'
config=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,target_modules=regex,bias='none',task_type='CAUSAL_LM')
model=get_peft_model(model,config);model.print_trainable_parameters();model.train()
optimizer=torch.optim.AdamW([v for v in model.parameters() if v.requires_grad],lr=a.learning_rate,weight_decay=0)
rows=[json.loads(line) for line in train_bytes.decode().splitlines()]
valid=[json.loads(line) for line in validation_bytes.decode().splitlines()]
provenance = {
    'provenance_version': 1, 'script': script_fingerprint, 'base_artifacts': base_fingerprint,
    'python_version': platform.python_version(), 'dependency_versions': package_versions,
    'host': platform.node(), 'platform': platform.platform(),
    'dataset_sha256': hashlib.sha256(train_bytes).hexdigest(),
    'validation_sha256': hashlib.sha256(validation_bytes).hexdigest(),
    'training_config': {
        'model_path': str(a.model.resolve()), 'data_path': str(a.data.resolve()),
        'output_path': str(a.output.resolve()), 'steps': a.steps, 'threads': a.threads,
        'interop_threads': 1, 'max_seq_length': a.max_seq_length, 'learning_rate': a.learning_rate,
        'seed': 17, 'device': 'cpu', 'dtype': 'bfloat16', 'attention_implementation': 'eager',
        'optimizer': {'class': 'torch.optim.AdamW', **optimizer.defaults},
        'batch_size': 1, 'gradient_accumulation_steps': 1, 'gradient_clip_norm': 1.0,
        'shuffle': 'one seeded permutation, cycled unchanged', 'checkpoint_interval_steps': 24,
        'thinking': False, 'loss': 'assistant-only cross entropy, per-example mean',
        'lora': {'r': 8, 'alpha': 16, 'dropout': 0.0, 'bias': 'none',
                 'task_type': 'CAUSAL_LM', 'target_regex': regex},
    },
}
(a.output / 'run-provenance.json').write_text(json.dumps(provenance, indent=2))

def encode(row):
    kwargs={'tools':row['tools'],'tokenize':True,'enable_thinking':False}
    full=tokenizer.apply_chat_template(row['messages'],add_generation_prompt=False,**kwargs)
    prefix=tokenizer.apply_chat_template(row['messages'][:-1],add_generation_prompt=True,**kwargs)
    if isinstance(full,Mapping):full=full['input_ids']
    if isinstance(prefix,Mapping):prefix=prefix['input_ids']
    if len(full)>a.max_seq_length:raise ValueError('Example exceeds the configured context; no silent truncation.')
    # BPE may merge the last prompt newline with the first tool token. Mask the
    # exact shared token prefix, after checking the un-tokenized template boundary.
    rendered=tokenizer.apply_chat_template(row['messages'],tools=row['tools'],enable_thinking=False,tokenize=False,add_generation_prompt=False)
    prompt=tokenizer.apply_chat_template(row['messages'][:-1],tools=row['tools'],enable_thinking=False,tokenize=False,add_generation_prompt=True)
    if not rendered.startswith(prompt):raise ValueError('Template boundary mismatch')
    shared=0
    for left,right in zip(full,prefix):
        if left!=right:break
        shared+=1
    if len(prefix)-shared>8:raise ValueError('Unexpected tokenization boundary mismatch')
    return torch.tensor([full]),shared
# Validate every record before the first optimization, never inspect the test split here.
encoded=[encode(row) for row in rows];validation=[encode(row) for row in valid]

def loss_for(item):
    ids,prefix=item
    positions=torch.arange(prefix-1,ids.shape[1]-1)
    output=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,logits_to_keep=positions)
    return torch.nn.functional.cross_entropy(output.logits.float().reshape(-1,output.logits.shape[-1]),ids[:,prefix:].reshape(-1))

def validate():
    model.eval()
    with torch.no_grad():losses=[float(loss_for(item)) for item in validation]
    model.train();return sum(losses)/len(losses)

started=time.monotonic();metrics=[]
base_validation=validate();print(json.dumps({'baseline_validation_loss':base_validation}),flush=True)
order=list(range(len(encoded)));random.shuffle(order)
for step in range(a.steps):
    # Stop safely if other services begin to need available RAM; cgroup remains the hard ceiling.
    if psutil.virtual_memory().available<psutil.virtual_memory().total*.10:raise RuntimeError('Spare-memory floor reached; no production service was stopped.')
    start=time.monotonic();optimizer.zero_grad(set_to_none=True)
    item=encoded[order[step%len(order)]]
    loss=loss_for(item)
    if not torch.isfinite(loss):raise RuntimeError('Non-finite training loss')
    loss.backward();torch.nn.utils.clip_grad_norm_([v for v in model.parameters() if v.requires_grad],1.0);optimizer.step()
    metric={'step':step+1,'loss':float(loss.detach()),'seconds':round(time.monotonic()-start,3),'rss_bytes':psutil.Process().memory_info().rss}
    metrics.append(metric);print(json.dumps(metric),flush=True)
    if (step+1)%24==0:model.save_pretrained(a.output/f'checkpoint-{step+1}')
model.save_pretrained(a.output/'final');tokenizer.save_pretrained(a.output/'final')
final_validation=validate()
report={'host':platform.node(),'platform':platform.platform(),'device':'cpu','dtype':'bfloat16','threads':a.threads,'steps':a.steps,'seed':17,'lora_rank':8,'lora_alpha':16,'target_regex':regex,'trainable_parameters':sum(v.numel() for v in model.parameters() if v.requires_grad),'model_path':str(a.model),'dataset_sha256':provenance['dataset_sha256'],'validation_sha256':provenance['validation_sha256'],'baseline_validation_loss':base_validation,'final_validation_loss':final_validation,'duration_seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'steps_metrics':metrics,'deployment_status':'NOT DEPLOYED; held-out Colibri evaluation required'}
report.update(provenance)
(a.output/'training-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='steps_metrics'},indent=2))
