"""Two optimizer steps on the longest training row; Linux server only.
Does not alter existing checkpoints, inspect held-out labels, or activate models.
"""
import argparse
import hashlib
import json
import math
import os
import platform
import re
import resource
import time
from collections.abc import Mapping
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=10)
    parser.add_argument('--dtype', choices=('bfloat16', 'float32'), default='bfloat16')
    parser.add_argument('--layers', type=int, default=24)
    parser.add_argument('--rank', type=int, default=16)
    parser.add_argument('--alpha', type=float, default=32)
    parser.add_argument('--gradient-checkpointing', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--semantic-loss-weight', type=float, default=1.0)
    parser.add_argument('--learning-rate', type=float, default=0.0001)
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.environ.get('CHAT_AI_TRAINING_SERVER') != '1':
        raise SystemExit('Capacity probing is restricted to the approved Linux server')
    if args.output.exists() or not 1 <= args.threads <= 14:
        raise SystemExit('New output file and 1–14 CPU threads required')
    if not math.isfinite(args.semantic_loss_weight) or args.semantic_loss_weight < 1 or not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        raise SystemExit('Finite semantic weight >= 1 and positive learning rate required')
    manifest = json.loads((args.data/'manifest.json').read_text())
    payload = (args.data/'train.jsonl').read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest['files']['train.jsonl'] or set(manifest['languages']) != {'en','fr'}:
        raise SystemExit('Dataset hash/language mismatch')
    if not set(manifest['applications']) <= {'facturation','management_projet','design_workflow'}:
        raise SystemExit('Unexpected application scope')
    import psutil
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
    from text_lora import configure_text_lora
    from semantic_loss import semantic_token_weights
    def check_memory():
        available = psutil.virtual_memory()
        if available.available < available.total*.10:
            raise RuntimeError('Spare-memory floor reached')
        return available.available
    check_memory()
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(17)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    encoded = []
    for line in payload.decode().splitlines():
        row = json.loads(line)
        kwargs = {'tools':row['tools'], 'enable_thinking':False}
        text = tokenizer.apply_chat_template(row['messages'], tokenize=False, add_generation_prompt=False, **kwargs)
        prompt = tokenizer.apply_chat_template(row['messages'][:-1], tokenize=False, add_generation_prompt=True, **kwargs)
        if not text.startswith(prompt):raise ValueError('Template boundary mismatch')
        ids = tokenizer(text, add_special_tokens=False)['input_ids']
        prefix = tokenizer(prompt, add_special_tokens=False)['input_ids']
        shared = 0
        for x,y in zip(ids,prefix):
            if x!=y:break
            shared+=1
        if len(prefix)-shared>8 or shared>=len(ids):raise ValueError('Token boundary mismatch')
        offsets=tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        if offsets['input_ids']!=ids:raise ValueError('Offset/token mismatch')
        weights=semantic_token_weights(text,len(prompt),offsets['offset_mapping'],shared,args.semantic_loss_weight)
        if len(weights)!=len(ids)-shared:raise ValueError('Weight/token mismatch')
        encoded.append((ids,shared,weights))
    ids, prefix, weights = max(encoded,key=lambda item:len(item[0]))
    if len(ids)>8192:raise ValueError('Context exceeded')
    model = Qwen3_5ForConditionalGeneration.from_pretrained(args.model, local_files_only=True,
        dtype=getattr(torch, args.dtype), attn_implementation='sdpa')
    model, regex = configure_text_lora(model, layers=args.layers, rank=args.rank, alpha=args.alpha, checkpointing=args.gradient_checkpointing)
    model.train()
    trainable = {name:value for name,value in model.named_parameters() if value.requires_grad}
    optimizer = torch.optim.AdamW(trainable.values(), lr=args.learning_rate, weight_decay=0)
    ids = torch.tensor([ids])
    weights = torch.tensor(weights,dtype=torch.float32)
    positions = torch.arange(prefix-1, ids.shape[1]-1)
    steps = []
    expected = set(range(model.config.text_config.num_hidden_layers-args.layers,model.config.text_config.num_hidden_layers))
    for step in range(2):
        free = check_memory()
        started=time.monotonic()
        optimizer.zero_grad(set_to_none=True)
        output=model(input_ids=ids, attention_mask=torch.ones_like(ids),use_cache=False,logits_to_keep=positions)
        per_token=torch.nn.functional.cross_entropy(output.logits.float().reshape(-1,output.logits.shape[-1]),ids[:,prefix:].reshape(-1),reduction='none')
        loss=(per_token*weights).sum()/weights.sum()
        unweighted_loss=per_token.mean()
        if not torch.isfinite(loss):raise RuntimeError('Non-finite loss')
        loss.backward()
        seen=set(); nonzero=set()
        for name,value in trainable.items():
            if value.grad is None or not torch.isfinite(value.grad).all():raise RuntimeError('Missing or non-finite gradient: '+name)
            layer=int(re.search(r'language_model\.layers\.(\d+)\.',name).group(1))
            seen.add(layer)
            if value.grad.abs().max()>0:nonzero.add(layer)
        if seen != expected or nonzero != expected:raise RuntimeError('Incomplete layer gradient coverage')
        # B starts at zero. Each intended layer must make a genuine parameter update.
        before={name:value.detach().clone() for name,value in trainable.items() if 'lora_B' in name}
        norm=torch.nn.utils.clip_grad_norm_(list(trainable.values()),1.0,error_if_nonfinite=True)
        optimizer.step()
        updated={int(re.search(r'language_model\.layers\.(\d+)\.',name).group(1))
                 for name,value in trainable.items() if name in before and not torch.equal(before[name],value.detach())}
        if updated != expected:raise RuntimeError('Incomplete adapter updates')
        if any(not torch.isfinite(value).all() for value in trainable.values()):raise RuntimeError('Non-finite parameter update')
        state_values=[value for state in optimizer.state.values() for value in state.values() if torch.is_tensor(value)]
        if any(not torch.isfinite(value).all() for value in state_values):raise RuntimeError('Non-finite optimizer state')
        metric={'step':step+1,'loss':float(loss.detach()),'unweighted_loss':float(unweighted_loss.detach()),'gradient_norm':float(norm),
            'seconds':time.monotonic()-started,'rss_bytes':psutil.Process().memory_info().rss,
            'available_memory_before_bytes':free,'available_memory_after_bytes':check_memory(),
            'gradient_layers':sorted(seen),'nonzero_gradient_layers':sorted(nonzero),'updated_layers':sorted(updated),
            'optimizer_state_entries':len(optimizer.state),'optimizer_state_bytes':sum(v.numel()*v.element_size() for v in state_values)}
        steps.append(metric); print(json.dumps(metric),flush=True)
        del output, loss, per_token, unweighted_loss, before, state_values
    report={'scope':'Capacity only; not model accuracy or production acceptance','model_path':str(args.model),
        'dataset_sha256':hashlib.sha256(payload).hexdigest(),'torch_version':torch.__version__,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'lora_setup_sha256':hashlib.sha256(Path(__file__).with_name('text_lora.py').read_bytes()).hexdigest(),
        'threads':args.threads,'dtype':args.dtype,'sequence_tokens':ids.shape[1],'lora_rank':args.rank,'lora_alpha':args.alpha,
        'lora_layers':args.layers,'target_regex':regex,'gradient_checkpointing':'nonreentrant' if args.gradient_checkpointing else False,'attention':'sdpa',
        'learning_rate':args.learning_rate,'semantic_loss_weight':args.semantic_loss_weight,
        'semantic_loss_sha256':hashlib.sha256(Path(__file__).with_name('semantic_loss.py').read_bytes()).hexdigest(),
        'trainable_parameters':sum(v.numel() for v in trainable.values()),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'steps':steps,'passed':True}
    with args.output.open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({'passed':True,'peak_rss_kib':report['peak_rss_kib']}),flush=True)

if __name__=='__main__':main()
