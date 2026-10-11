"""Validate synthetic SFT labels against the exact tokenizer and Colibri parser.
Only tokenizer metadata is loaded; no model weights, database or inference API.
Run before training with the intended inference runtime snapshot.
"""
import argparse, hashlib, json, sys
from collections.abc import Mapping
from pathlib import Path
from jsonschema import validate
from semantic_loss import semantic_token_weights


def verify_split(payload, tools_parser, tokenizer, maximum_tokens, runtime_renderer, semantic_weight=1):
    rows=[json.loads(line) for line in payload.decode().splitlines()]
    if not rows:raise ValueError('Empty dataset split')
    maximum=0
    for row in rows:
        target=row['messages'][-1]
        if target.get('role')!='assistant' or len(target.get('tool_calls',[]))!=1:raise ValueError('Exactly one assistant tool target is required')
        expected=target['tool_calls'][0]['function']
        declared={t['function']['name']:t['function']['parameters'] for t in row['tools']}
        if expected['name'] not in declared:raise ValueError('Target operation is not offered')
        validate(expected['arguments'],declared[expected['name']])
        options={'tools':row['tools'],'enable_thinking':False,'tokenize':False}
        full=tokenizer.apply_chat_template(row['messages'],add_generation_prompt=False,**options)
        prefix=tokenizer.apply_chat_template(row['messages'][:-1],add_generation_prompt=True,**options)
        if not full.startswith(prefix):raise ValueError('Chat-template target boundary mismatch')
        runtime_prefix=runtime_renderer(row['messages'][:-1],enable_thinking=False,tools=row['tools'],add_generation_prompt=True)
        if prefix!=runtime_prefix:raise ValueError('Tokenizer/Colibri generation-prefix mismatch')
        _,calls=tools_parser(full[len(prefix):],row['tools'])
        if len(calls)!=1 or calls[0]['function']['name']!=expected['name'] or json.loads(calls[0]['function']['arguments'])!=expected['arguments']:raise ValueError('Tool argument round-trip mismatch')
        tokens=tokenizer.apply_chat_template(row['messages'],tools=row['tools'],enable_thinking=False,tokenize=True,add_generation_prompt=False)
        if isinstance(tokens,Mapping):tokens=tokens['input_ids']
        prompt_tokens=tokenizer.apply_chat_template(row['messages'][:-1],tools=row['tools'],enable_thinking=False,tokenize=True,add_generation_prompt=True)
        if isinstance(prompt_tokens,Mapping):prompt_tokens=prompt_tokens['input_ids']
        shared=0
        for left,right in zip(tokens,prompt_tokens):
            if left!=right:break
            shared+=1
        if not shared or len(prompt_tokens)-shared>8 or shared>=len(tokens):raise ValueError('Unexpected tokenization loss boundary')
        offsets=tokenizer(full,add_special_tokens=False,return_offsets_mapping=True)
        if offsets['input_ids']!=tokens:raise ValueError('Offset/template token-ID mismatch')
        weights=semantic_token_weights(full,len(prefix),offsets['offset_mapping'],shared,semantic_weight)
        if len(weights)!=len(tokens)-shared:raise ValueError('Semantic loss-token mismatch')
        maximum=max(maximum,len(tokens))
        if len(tokens)>maximum_tokens:raise ValueError('Example exceeds context; no truncation permitted')
    return {'count':len(rows),'round_trip_passed':len(rows),'runtime_prefix_parity_passed':len(rows),'loss_boundary_passed':len(rows),'semantic_alignment_passed':len(rows),'semantic_loss_weight':semantic_weight,'maximum_tokens':maximum,'sha256':hashlib.sha256(payload).hexdigest()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--max-tokens',type=int,default=8192)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--semantic-loss-weight',type=float,default=1)
    args=parser.parse_args()
    if args.max_tokens<1:raise SystemExit('Positive context budget required')
    manifest=json.loads((args.data/'manifest.json').read_text())
    if set(manifest.get('languages',[]))!={'en','fr'}:raise SystemExit('English/French-only scope required')
    payloads={name:(args.data/name).read_bytes() for name in ['train.jsonl','valid.jsonl']}
    for name,payload in payloads.items():
        if hashlib.sha256(payload).hexdigest()!=manifest.get('files',{}).get(name):raise SystemExit('Dataset manifest mismatch: '+name)
    # The runtime path is trusted operator input. This selects the actual parser,
    # not a rewritten mock, while leaving its model-serving entry point unused.
    sys.path.insert(0,str(args.runtime/'c'))
    from openai_server import parse_qwen_tool_calls, render_chat_qwen
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    report={name:verify_split(payload,parse_qwen_tool_calls,tokenizer,args.max_tokens,render_chat_qwen,args.semantic_loss_weight) for name,payload in payloads.items()}
    report['scope']='Tokenizer/template/parser checks only; not model accuracy or training success'
    if args.output:
        with args.output.open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
