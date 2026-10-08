"""Evaluate native Colibri tool calls; never execute business actions."""
import argparse, collections, hashlib, json, math, platform, statistics, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from chat_ai_assistant.provider import ChatAIModelService,ModelConfig
from chat_ai_assistant.contracts import ChatAITool,ChatAIToolRegistry,ChatAIError
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18090/v1');p.add_argument('--label',required=True);p.add_argument('--dataset',type=Path,default=ROOT/'training/datasets/facturation/test.eval.jsonl');p.add_argument('--max-tokens',type=int,default=512);a=p.parse_args()
schemas=json.loads((ROOT/'training/tool-schemas.json').read_text())
registry=ChatAIToolRegistry([ChatAITool(t['function']['name'],t['function']['description'],t['function']['parameters'],{'type':'object'},t['function']['name'],classification='proposal' if t['function']['name']=='prepare_change' else 'read') for t in schemas])
class MeasuredModel(ChatAIModelService):
    def stream(self,*args,**kwargs):
        self.started=time.monotonic();self.ttft=None
        for delta in super().stream(*args,**kwargs):
            if self.ttft is None and (delta.get('content') or delta.get('tool_calls')):self.ttft=time.monotonic()-self.started
            yield delta
model=MeasuredModel(ModelConfig(a.url,'chat-ai-facturation',mode='native',max_tokens=a.max_tokens))
rows=[];out=ROOT/'training/evaluations'/a.label;out.mkdir(exist_ok=True)
def args_match(expected,actual,tool):
    if tool=='clarify':return bool(actual.get('message'))
    if tool=='knowledge':return isinstance(actual.get('query'),str) and bool(actual['query'].strip())
    actual=dict(actual)
    if actual.get('limit')==10:actual.pop('limit')
    if actual.get('offset')==0:actual.pop('offset')
    if actual.get('unpaid') is False:actual.pop('unpaid')
    return actual==expected
for row in [json.loads(line) for line in a.dataset.read_text().splitlines()]:
    start=time.monotonic();result={'id':row['id'],'category':row['category'],'language':row['language'],'expected':row['expected'],'tool_correct':False,'arguments_correct':False,'structured_valid':False}
    try:
        action,usage=model.choose(row['messages'],list(registry.tools.values()))
        result.update(action=action,usage=usage)
        if action['tool']!='clarify':registry.validate(action['tool'],action['arguments'])
        result['structured_valid']=True
        result['tool_correct']=action['tool']==row['expected']['tool']
        result['arguments_correct']=result['tool_correct'] and args_match(row['expected']['arguments'],{'message':action.get('message')} if action['tool']=='clarify' else action['arguments'],action['tool'])
    except Exception as exc:result['error']=getattr(exc,'code',type(exc).__name__)
    elapsed=time.monotonic()-start;result['latency_s']=round(elapsed,3);result['ttft_s']=round(model.ttft,3) if model.ttft is not None else None
    generated=result.get('usage',{}).get('completion_tokens',0)
    result['completion_tokens_per_wall_second']=round(generated/elapsed,2) if generated else None
    rows.append(result)
    with (out/'cases.jsonl').open('a') as file:file.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(f"{row['id']} tool={result['tool_correct']} args={result['arguments_correct']} latency={elapsed:.1f}s",flush=True)
def summarize(items):
    return {'count':len(items),**{key:round(100*sum(x[key] for x in items)/len(items),2) for key in ['tool_correct','arguments_correct','structured_valid']}}
latencies=sorted(row['latency_s'] for row in rows)
report={'label':a.label,'runtime':'Colibri CPU only, 4 threads, native tools, thinking off, max output '+str(a.max_tokens),'platform':platform.platform(),'dataset_sha256':hashlib.sha256(a.dataset.read_bytes()).hexdigest(),'metrics':summarize(rows),'latency_mean_s':round(statistics.mean(latencies),3),'latency_p95_s':latencies[math.ceil(.95*len(rows))-1],'time_to_first_visible_event_mean_s':statistics.mean(x['ttft_s'] for x in rows if x['ttft_s'] is not None),'completion_tokens_per_wall_second_mean':statistics.mean(x['completion_tokens_per_wall_second'] for x in rows if x['completion_tokens_per_wall_second'] is not None),'by_language':{lang:summarize([x for x in rows if x['language']==lang]) for lang in ['en','fr','ar','ary']},'by_category':{c:summarize([x for x in rows if x['category']==c]) for c in sorted(set(x['category'] for x in rows))},'limitations':['48 synthetic prompts, 12 groups, not a statistical guarantee.','Knowledge/clarification arguments checked for schema and nonempty text; explanation factuality requires separate review.','No business tools executed; backend permission tests are separate.','Native tool calls are buffered by the runtime. First visible event is not first generated token. Report end-to-end token throughput; raw decode throughput is unavailable.']}
(out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
