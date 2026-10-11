"""Server-only bounded CPU LoRA. Never uses production data or activates an adapter."""
import argparse, hashlib, json, os, platform, random, resource, time
from pathlib import Path
from collections.abc import Mapping
from importlib import metadata
from training_schedule import complete_epoch_order
from text_lora import configure_text_lora
from semantic_loss import semantic_token_weights


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


p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=96);p.add_argument('--threads',type=int,default=14);p.add_argument('--max-seq-length',type=int,default=4096);p.add_argument('--learning-rate',type=float,default=0.0001);p.add_argument('--balanced-applications',action='store_true');p.add_argument('--lora-layers',type=int,default=4);p.add_argument('--lora-rank',type=int,default=8);p.add_argument('--lora-alpha',type=float,default=16);p.add_argument('--gradient-checkpointing',action='store_true');p.add_argument('--semantic-loss-weight',type=float,default=1.0);p.add_argument('--complete-epochs',type=int);p.add_argument('--attention',choices=['eager','sdpa'],default='eager');a=p.parse_args()
if platform.system()!='Linux' or os.environ.get('CHAT_AI_TRAINING_SERVER')!='1':raise SystemExit('Training is restricted to the approved Linux server.')
dataset_manifest=json.loads((a.data/'manifest.json').read_text())
if set(dataset_manifest.get('languages',[]))!={'en','fr'}:raise SystemExit('Current training scope requires an English/French-only dataset manifest.')
train_bytes = (a.data / 'train.jsonl').read_bytes()
validation_bytes = (a.data / 'valid.jsonl').read_bytes()
for name,payload in [('train.jsonl',train_bytes),('valid.jsonl',validation_bytes)]:
    expected_hash=dataset_manifest.get('files',{}).get(name)
    if not expected_hash or hashlib.sha256(payload).hexdigest()!=expected_hash:
        raise SystemExit('Dataset does not match its validated manifest: '+name)
if a.complete_epochs is not None:
    if a.complete_epochs<1 or a.balanced_applications:raise SystemExit('Complete epochs must be positive and cannot use oversampling.')
    a.steps=a.complete_epochs*len(train_bytes.decode().splitlines())
rows=[json.loads(line) for line in train_bytes.decode().splitlines()]
valid=[json.loads(line) for line in validation_bytes.decode().splitlines()]
if not rows or not valid:raise SystemExit('Training and validation splits must be nonempty.')
declared=set(dataset_manifest.get('applications',['facturation']))
if not declared or not declared<={'facturation','management_projet','design_workflow'}:raise SystemExit('Unexpected application training scope.')
for split in (rows,valid):
    if {row.get('application','facturation') for row in split}!=declared:raise SystemExit('Application metadata does not match the manifest.')
import torch
from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
import psutil
if psutil.virtual_memory().available<psutil.virtual_memory().total*.10:raise SystemExit('Insufficient spare memory; training not started.')
if not 1 <= a.semantic_loss_weight < float('inf'):raise SystemExit('Semantic loss weight must be finite and at least one.')
if a.steps <= 0 or a.threads <= 0 or a.max_seq_length <= 0 or not 0 < a.learning_rate < float('inf'):
    raise SystemExit('Training steps, threads, context and learning rate must be positive and finite.')
script_fingerprint = file_fingerprint(Path(__file__))
base_fingerprint = model_fingerprint(a.model)
package_versions = dict(sorted((distribution.metadata['Name'], distribution.version)
                               for distribution in metadata.distributions() if distribution.metadata['Name']))
torch.set_num_threads(a.threads);torch.set_num_interop_threads(1);torch.manual_seed(17);random.seed(17)
a.output.mkdir(parents=True,exist_ok=False)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
model=Qwen3_5ForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,attn_implementation=a.attention)
model,regex=configure_text_lora(model,layers=a.lora_layers,rank=a.lora_rank,alpha=a.lora_alpha,checkpointing=a.gradient_checkpointing)
model.print_trainable_parameters();model.train()
optimizer=torch.optim.AdamW([v for v in model.parameters() if v.requires_grad],lr=a.learning_rate,weight_decay=0)
provenance = {
    'provenance_version': 1, 'script': script_fingerprint, 'schedule_script': file_fingerprint(Path(__file__).with_name('training_schedule.py')), 'lora_setup_script': file_fingerprint(Path(__file__).with_name('text_lora.py')), 'semantic_loss_script': file_fingerprint(Path(__file__).with_name('semantic_loss.py')), 'base_artifacts': base_fingerprint,
    'python_version': platform.python_version(), 'dependency_versions': package_versions,
    'host': platform.node(), 'platform': platform.platform(),
    'dataset_sha256': hashlib.sha256(train_bytes).hexdigest(),
    'validation_sha256': hashlib.sha256(validation_bytes).hexdigest(),
    'training_config': {
        'model_path': str(a.model.resolve()), 'data_path': str(a.data.resolve()),
        'output_path': str(a.output.resolve()), 'steps': a.steps, 'threads': a.threads,
        'interop_threads': 1, 'max_seq_length': a.max_seq_length, 'learning_rate': a.learning_rate,
        'complete_epochs': a.complete_epochs, 'seed': 17, 'device': 'cpu', 'dtype': 'bfloat16', 'attention_implementation': a.attention,
        'optimizer': {'class': 'torch.optim.AdamW', **optimizer.defaults},
        'batch_size': 1, 'gradient_accumulation_steps': 1, 'gradient_clip_norm': 1.0,
        'shuffle': 'complete independently reshuffled epochs, proportionally interleaved applications' if a.complete_epochs else 'seeded per-application permutations, alternating applications' if a.balanced_applications else 'one seeded permutation, cycled unchanged', 'checkpoint_interval_steps': 24,
        'thinking': False, 'gradient_checkpointing': 'nonreentrant' if a.gradient_checkpointing else False, 'loss': 'assistant-only cross entropy, semantic-token weighted per-example mean' if a.semantic_loss_weight>1 else 'assistant-only cross entropy, per-example mean', 'semantic_loss_weight': a.semantic_loss_weight,
        'lora': {'r': a.lora_rank, 'alpha': a.lora_alpha, 'dropout': 0.0, 'bias': 'none',
                 'task_type': 'CAUSAL_LM', 'target_regex': regex, 'layers': a.lora_layers},
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
    offset_encoding=tokenizer(rendered,add_special_tokens=False,return_offsets_mapping=True)
    if offset_encoding['input_ids']!=full:raise ValueError('Offset tokenizer does not match chat-template token IDs')
    weights=semantic_token_weights(rendered,len(prompt),offset_encoding['offset_mapping'],shared,a.semantic_loss_weight)
    if len(weights)!=len(full)-shared:raise ValueError('Loss-weight/token alignment mismatch')
    return torch.tensor([full]),shared,torch.tensor(weights,dtype=torch.float32)
# Validate every record before the first optimization, never inspect the test split here.
encoded=[encode(row) for row in rows];validation=[encode(row) for row in valid]

def loss_for(item,include_unweighted=False):
    ids,prefix,weights=item
    positions=torch.arange(prefix-1,ids.shape[1]-1)
    output=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,logits_to_keep=positions)
    per_token=torch.nn.functional.cross_entropy(output.logits.float().reshape(-1,output.logits.shape[-1]),ids[:,prefix:].reshape(-1),reduction='none')
    weighted=(per_token*weights).sum()/weights.sum()
    return (weighted,per_token.mean()) if include_unweighted else weighted

def validate():
    if not validation:raise ValueError('Empty validation split')
    model.eval()
    with torch.no_grad():pairs=[tuple(float(v) for v in loss_for(item,include_unweighted=True)) for item in validation]
    losses=[pair[0] for pair in pairs];raw_losses=[pair[1] for pair in pairs]
    model.train()
    by_application={}
    for row,loss in zip(valid,losses):by_application.setdefault(row.get('application','facturation'),[]).append(loss)
    averages={app:sum(values)/len(values) for app,values in by_application.items()}
    raw_groups={}
    for row,loss in zip(valid,raw_losses):raw_groups.setdefault(row.get('application','facturation'),[]).append(loss)
    raw_averages={app:sum(values)/len(values) for app,values in raw_groups.items()}
    return {'micro':sum(losses)/len(losses),'by_application':averages,'macro':sum(averages.values())/len(averages),
            'unweighted':{'micro':sum(raw_losses)/len(raw_losses),'by_application':raw_averages,'macro':sum(raw_averages.values())/len(raw_averages)}}

started=time.monotonic();metrics=[]
base_validation=validate();print(json.dumps({'baseline_validation_loss':base_validation}),flush=True)
order=complete_epoch_order(rows) if a.complete_epochs else list(range(len(encoded)))
if not a.complete_epochs:random.shuffle(order)
if a.balanced_applications:
    declared=set(dataset_manifest.get('applications',[]))
    if not {'facturation'}<=declared or len(declared)<2 or not declared<={'facturation','management_projet','design_workflow'}:raise ValueError('Balanced training requires declared approved applications and retained Facturation examples.')
    groups={}
    for index,row in enumerate(rows):
        app=row.get('application')
        if app not in declared:raise ValueError('Unexpected or missing application metadata in training source.')
        groups.setdefault(app,[]).append(index)
    if set(groups)!=declared:raise ValueError('Every declared application must be represented.')
    for indices in groups.values():random.shuffle(indices)
    applications=sorted(groups)
    order=[groups[app][turn%len(groups[app])] for turn in range(max(map(len,groups.values()))) for app in applications]
exposure={};unique_exposure={}
for step in range(a.steps):
    # Stop safely if other services begin to need available RAM; cgroup remains the hard ceiling.
    if psutil.virtual_memory().available<psutil.virtual_memory().total*.10:raise RuntimeError('Spare-memory floor reached; no production service was stopped.')
    start=time.monotonic();optimizer.zero_grad(set_to_none=True)
    if a.complete_epochs and step and step%len(order)==0:order=complete_epoch_order(rows,epoch=step//len(order))
    selected_index=order[step%len(order)]
    application=rows[selected_index].get('application','facturation')
    exposure[application]=exposure.get(application,0)+1
    unique_exposure.setdefault(application,set()).add(selected_index)
    item=encoded[selected_index]
    loss=loss_for(item)
    if not torch.isfinite(loss):raise RuntimeError('Non-finite training loss')
    loss.backward();torch.nn.utils.clip_grad_norm_([v for v in model.parameters() if v.requires_grad],1.0,error_if_nonfinite=True);optimizer.step()
    metric={'step':step+1,'loss':float(loss.detach()),'seconds':round(time.monotonic()-start,3),'rss_bytes':psutil.Process().memory_info().rss}
    metrics.append(metric);print(json.dumps(metric),flush=True)
    if (step+1)%24==0:model.save_pretrained(a.output/f'checkpoint-{step+1}')
model.save_pretrained(a.output/'final');tokenizer.save_pretrained(a.output/'final')
final_validation=validate()
report={'host':platform.node(),'platform':platform.platform(),'device':'cpu','dtype':'bfloat16','threads':a.threads,'steps':a.steps,'seed':17,'lora_rank':a.lora_rank,'lora_alpha':a.lora_alpha,'target_regex':regex,'trainable_parameters':sum(v.numel() for v in model.parameters() if v.requires_grad),'model_path':str(a.model),'dataset_sha256':provenance['dataset_sha256'],'validation_sha256':provenance['validation_sha256'],'baseline_validation_loss':base_validation['micro'],'final_validation_loss':final_validation['micro'],'baseline_validation_unweighted_loss':base_validation['unweighted']['micro'],'final_validation_unweighted_loss':final_validation['unweighted']['micro'],'baseline_validation_by_application':base_validation,'final_validation_by_application':final_validation,'duration_seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'steps_metrics':metrics,'deployment_status':'NOT DEPLOYED; held-out Colibri evaluation required'}
report.update(provenance)
report['application_exposure']={app:{'steps':count,'unique_examples':len(unique_exposure[app])} for app,count in exposure.items()}
(a.output/'training-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='steps_metrics'},indent=2))
