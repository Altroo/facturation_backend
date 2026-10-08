"""CPU/latency/concurrency probe using synthetic validation prompts, no business tools."""
import argparse, json, math, platform, statistics, subprocess, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psutil

p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--unit',required=True);p.add_argument('--url',default='http://127.0.0.1:18104');p.add_argument('--output',type=Path,required=True);p.add_argument('--model-manifest',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise SystemExit('Refusing to replace an existing benchmark.')
manifest=json.loads(a.model_manifest.read_text())
rows=[json.loads(s) for s in (a.dataset/'valid.eval.jsonl').read_text().splitlines()]
if any(row.get('language') not in ('en','fr') for row in rows):raise SystemExit('Current performance evaluation scope is English/French only.')
schemas={t['function']['name']:t for t in json.loads((a.dataset/'tool-schemas.json').read_text())}
# Clarification definition is copied from frozen training payload, not recreated.
first=json.loads((a.dataset/'valid.jsonl').read_text().splitlines()[0]);clarify=next(t for t in first['tools'] if t['function']['name']=='clarify')
parent=psutil.Process(int(subprocess.check_output(['systemctl','show',a.unit,'--property=MainPID','--value'])))
def snapshot():
    procs=[parent]+parent.children(recursive=True);rss=cpu=0
    for proc in procs:
        try:
            rss+=proc.memory_info().rss;t=proc.cpu_times();cpu+=t.user+t.system
        except psutil.NoSuchProcess:pass
    return rss,cpu

def get(path):
    with urllib.request.urlopen(a.url+path,timeout=5) as response:return json.load(response)

def request(row):
    payload={'model':manifest['model_id'],'messages':row['messages'],'tools':(row.get('offered_tool_schemas') or [schemas[n] for n in row['offered_tools']])+[clarify],'tool_choice':'auto','temperature':0,'max_tokens':512,'enable_thinking':False,'chat_template_kwargs':{'enable_thinking':False},'stream':True,'stream_options':{'include_usage':True}}
    req=urllib.request.Request(a.url+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    t=time.monotonic();usage={};first_event=None;finish=None;error=None
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            for line in response:
                if time.monotonic()-t>120:raise TimeoutError('Total request deadline')
                if not line.startswith(b'data: '):continue
                raw=line[6:].strip()
                if raw==b'[DONE]':break
                event=json.loads(raw);usage.update(event.get('usage') or {})
                for choice in event.get('choices',[]):
                    delta=choice.get('delta',{})
                    if first_event is None and (delta.get('tool_calls') or delta.get('content')):first_event=time.monotonic()-t
                    finish=choice.get('finish_reason') or finish
                if 'error' in event:error=event['error'].get('code','stream_error')
        if finish not in ('stop','tool_calls'):error=error or 'incomplete_response'
    except Exception as exc:error=type(exc).__name__
    return {'id':row['id'],'language':row['language'],'latency_s':time.monotonic()-t,'first_visible_event_s':first_event,'usage':usage,'finish_reason':finish,'error':error}

before=get('/profile');health=get('/health')
if health['scheduler']['active'] or health['scheduler']['queued']:raise SystemExit('Endpoint is busy; do not contaminate another run.')
if health.get('kv_slots')!=1:raise SystemExit('This throughput probe requires a single decoder slot.')
threads=parent.environ().get('OMP_NUM_THREADS');quota=subprocess.check_output(['systemctl','show',a.unit,'--property=CPUQuotaPerSecUSec','--value'],text=True).strip()
initial_rss,initial_cpu=snapshot();samples=[];stop=threading.Event()
def sample():
    while not stop.wait(.25):samples.append({'time':time.monotonic(),'rss_bytes':snapshot()[0]})
thread=threading.Thread(target=sample,daemon=True);thread.start();start=time.monotonic()
sequential=[request(row) for row in rows[:4]]
concurrent=[]
for i in range(2):
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent.extend(pool.map(request,rows[i*2:2+i*2]))
wall=time.monotonic()-start;stop.set();thread.join();final_rss,final_cpu=snapshot();after=get('/profile')
turn_count=after['seq']-before['seq'];expected_turns=sum(bool(row['finish_reason']) for row in sequential+concurrent)
profile_attributed=turn_count==expected_turns and 0<=turn_count<=len(after['turns'])
turns=after['turns'][-turn_count:] if turn_count and profile_attributed else []
def metrics(cases):
    times=sorted(row['latency_s'] for row in cases)
    return {'count':len(cases),'mean_latency_s':statistics.mean(times),'p95_latency_s':times[math.ceil(.95*len(times))-1],'errors':sum(row['error'] is not None for row in cases)}
report={'inference_platform':platform.platform(),'model_manifest':manifest,'profile_attributed':profile_attributed,'logical_cpus':psutil.cpu_count(),'unit':a.unit,'threads_env':threads,'cpu_quota_systemd':quota,'model':manifest['model_id'],'sequential':metrics(sequential),'concurrency_two':metrics(concurrent),'cases':sequential+concurrent,'wall_s':wall,'process_cpu_seconds':final_cpu-initial_cpu,'average_busy_cpu_cores':(final_cpu-initial_cpu)/wall,'host_cpu_capacity_percent':100*(final_cpu-initial_cpu)/wall/psutil.cpu_count(),'rss_initial_bytes':initial_rss,'rss_peak_bytes':max([initial_rss,final_rss]+[x['rss_bytes'] for x in samples]),'host_memory_available_bytes':psutil.virtual_memory().available,'runtime_profile':turns,'weighted_decode_tokens_per_second':sum(t['completion_tokens'] for t in turns)/sum(t['wall_s'] for t in turns) if turns else None,'scheduler_before':health['scheduler'],'scheduler_after':get('/health')['scheduler'],'limitations':['Four synthetic validation prompts repeated sequentially then with concurrency two: small performance probe, not capacity certification. Concurrent pass runs second; model and prefix caches may be warm.','Runtime profile wall_s starts after prefill (qwen36.c q36_prepare); decode rate excludes prompt processing.','First visible event for native tool calls is buffered, not first generated token.','Tests inference directly; application serializes model requests with a database lease.','Existing production services were not stopped. No application business operations executed.']}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('sequential','concurrency_two','average_busy_cpu_cores','rss_peak_bytes','weighted_decode_tokens_per_second')},indent=2))
