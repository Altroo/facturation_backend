"""Evaluate frozen, permission-filtered tool schemas without executing business tools.
Input: JSON {label, dataset_sha256, rows}. Output: newline-delimited result/summary JSON.
Use --factory for an existing Django model provider, or --url/--model for an isolated
Colibri candidate. Authentication comes from operator configuration, never reports.
"""
import argparse,hashlib,importlib,json,math,os,statistics,sys,time
from dataclasses import replace
from chat_ai_assistant.provider import ChatAIModelService,ModelConfig
from chat_ai_assistant.contracts import ChatAITool
from chat_ai_assistant.clarifications import clarification_message

p=argparse.ArgumentParser()
p.add_argument('--factory');p.add_argument('--url');p.add_argument('--model')
p.add_argument('--max-tokens',type=int,default=512)
a=p.parse_args()
snapshot=json.load(sys.stdin)
if a.factory:
    import django
    django.setup()
    module,function=a.factory.split(':')
    original=getattr(importlib.import_module(module),function)()
    config=original.config
else:
    if not a.url or not a.model:raise SystemExit('Provide a provider factory or a private URL/model.')
    config=ModelConfig(a.url,a.model,api_key=os.environ.get('CHAT_AI_MODEL_API_KEY',''),mode='native',timeout=180,max_tokens=a.max_tokens)
class MeasuredModel(ChatAIModelService):
    def stream(self,*args,**kwargs):
        self.ttft=None;started=time.monotonic()
        for delta in super().stream(*args,**kwargs):
            if self.ttft is None and (delta.get('content') or delta.get('tool_calls')):self.ttft=time.monotonic()-started
            yield delta
model=MeasuredModel(config)
results=[]
def normalized(arguments):
    value=dict(arguments)
    for name,default in [('limit',10),('offset',0),('period','all_time'),('unpaid',False)]:
        if value.get(name)==default:value.pop(name,None)
    return value
for row in snapshot['rows']:
    tools=[ChatAITool(t['function']['name'],t['function']['description'],t['function']['parameters'],{'type':'object'},t['function']['name']) for t in row['offered_tool_schemas']]
    expected=row['expected'];tool=expected['tool']
    result={key:row[key] for key in ['id','category','language']}
    result.update(expected=expected,tool_correct=False,arguments_correct=False,structured_valid=False,exact_arguments_eligible=tool not in ('knowledge','clarify'))
    started=time.monotonic();model.ttft=None
    try:
        action,usage=model.choose(row['messages'],tools)
        result.update(action=action,usage=usage,structured_valid=True,tool_correct=action['tool']==tool)
        if tool=='clarify':match=action.get('message')==clarification_message(**expected['arguments'])
        elif tool=='knowledge':match=isinstance(action.get('arguments',{}).get('query'),str) and bool(action['arguments']['query'].strip())
        else:match=normalized(action.get('arguments',{}))==normalized(expected['arguments'])
        result['arguments_correct']=result['tool_correct'] and match
    except Exception as exc:result['error']=getattr(exc,'code',type(exc).__name__)
    elapsed=time.monotonic()-started
    result['latency_s']=round(elapsed,3);result['first_visible_event_s']=round(model.ttft,3) if model.ttft is not None else None
    generated=result.get('usage',{}).get('completion_tokens',0)
    result['completion_tokens_per_wall_second']=round(generated/elapsed,3) if generated else None
    results.append(result);print(json.dumps({'case':result},ensure_ascii=False),flush=True)
def metrics(items):
    if not items:return {'count':0}
    exact=[x for x in items if x['exact_arguments_eligible']]
    counts={name:sum(x[name] for x in items) for name in ['tool_correct','arguments_correct','structured_valid']}
    return {'count':len(items),'counts':counts,'percent':{name:round(100*value/len(items),2) for name,value in counts.items()},'exact_arguments':{'passed':sum(x['arguments_correct'] for x in exact),'count':len(exact),'percent':round(100*sum(x['arguments_correct'] for x in exact)/len(exact),2) if exact else None}}
latencies=sorted(x['latency_s'] for x in results)
visible=[x['first_visible_event_s'] for x in results if x['first_visible_event_s'] is not None]
throughput=[x['completion_tokens_per_wall_second'] for x in results if x['completion_tokens_per_wall_second'] is not None]
report={'label':snapshot['label'],'dataset_sha256':snapshot['dataset_sha256'],'model_id':config.model,'max_output_tokens':config.max_tokens,'thinking':config.thinking,'mode':config.mode,'metrics':metrics(results),'by_language':{language:metrics([x for x in results if x['language']==language]) for language in sorted({x['language'] for x in results})},'by_category':{category:metrics([x for x in results if x['category']==category]) for category in sorted({x['category'] for x in results})},'latency_mean_s':round(statistics.mean(latencies),3),'latency_p95_s':latencies[math.ceil(.95*len(latencies))-1],'first_visible_event_mean_s':round(statistics.mean(visible),3) if visible else None,'completion_tokens_per_wall_second_mean':round(statistics.mean(throughput),3) if throughput else None,'limitations':['Synthetic held-out scenarios; no business tools executed.','Knowledge query wording is scored only for nonempty schema-valid text; retrieval factuality is tested separately. Clarifications must match the expected reason and language.','Exact arguments exclude knowledge and clarification. Optional default pagination/period arguments are normalized.','Native Colibri tool buffering means first visible event and wall throughput are not raw decode TTFT/tokens per second.','No hostname, URL, key, private record or operator path is included in the report.']}
print(json.dumps({'summary':report},ensure_ascii=False),flush=True)
