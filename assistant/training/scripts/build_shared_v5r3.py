"""Combine reviewed native-metadata curricula; keep every frozen evaluation outside SFT."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT=Path(__file__).resolve().parents[2]
SOURCES={app:app.replace('_','-')+'-refinement-v2-en-fr' for app in ('facturation','management_projet','design_workflow')}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def key(app,text):return app+':'+re.sub(r'\W+',' ',unicodedata.normalize('NFKD',text).casefold()).strip()


def main():
    out=ROOT/'training/datasets/shared-v5r3-en-fr'
    if out.exists():raise ValueError('Never overwrite a frozen combined dataset')
    prior=ROOT/'training/datasets/shared-adapter-v2-en-fr'
    old=json.loads((prior/'manifest.json').read_text())
    held={}
    for filename,info in old['inputs'].items():
        path=prior/filename
        assert digest(path)==old['files'][filename]
        held[str(path.relative_to(ROOT))]={'sha256':digest(path),'count':info['count'],
            'baseline_label':info['evaluation_label'],'kind':'retained regression'}
    for app,source in SOURCES.items():
        path=ROOT/'training/datasets'/source/'independent.eval.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        held[str(path.relative_to(ROOT))]={'sha256':digest(path),'count':len(rows),
            'baseline_label':app.replace('_','-')+'-refinement-v2-baseline-v5r2','kind':'new frozen evaluation'}
    excluded=set()
    for relative,info in held.items():
        for row in map(json.loads,(ROOT/relative).read_text().splitlines()):
            context=json.loads(row['messages'][0]['content'].split('Trusted context: ',1)[1])
            excluded.add(key(context['application'],row['messages'][-1]['content']))
    counts={};pins={};payloads={};keys={}
    for split in ('train','valid'):
        combined=[];keys[split]=set()
        for app,source in SOURCES.items():
            folder=ROOT/'training/datasets'/source
            manifest=json.loads((folder/'manifest.json').read_text())
            assert manifest['generator_sha256']==digest(ROOT/'training/scripts/build_refinement_v2.py')
            assert manifest['languages']==['en','fr']
            pins[source+'/manifest.json']=digest(folder/'manifest.json')
            path=folder/(split+'.jsonl');assert digest(path)==manifest['files'][path.name]
            pins[source+'/'+path.name]=digest(path)
            rows=list(map(json.loads,path.read_text().splitlines()))
            for row in rows:
                assert row['messages'][-1]['role']=='assistant'
                prompt=next(m['content'] for m in reversed(row['messages']) if m['role']=='user')
                candidate=key(app,prompt)
                if candidate in keys[split] or candidate in excluded:raise ValueError('Duplicate or frozen prompt in SFT input')
                keys[split].add(candidate)
                combined.append({**row,'application':app})
            counts[app+'/'+split+'.jsonl']=len(rows)
        payloads[split+'.jsonl']=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in combined)
    assert not keys['train']&keys['valid'],'Training/validation overlap'
    for payload in payloads.values():
        assert not re.search(r'[\u0600-\u06ff]|BEGIN.{0,12}PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret)\s*[:=]',payload,re.I)
    report={'version':out.name,'applications':list(SOURCES),'languages':['en','fr'],
        'counts':counts,'sources':pins,'generator_sha256':digest(Path(__file__)),
        'files':{name:hashlib.sha256(raw.encode()).hexdigest() for name,raw in payloads.items()},
        'held_out':held,'held_out_count':sum(value['count'] for value in held.values()),
        'split_policy':'Existing 390 diagnostic rows unchanged and excluded from SFT; 48 new independently phrased EN/FR cases remain outside training and validation. Synthetic authoring by the implementation team, not a blind external evaluation. Failure categories informed adaptation. Exact normalized overlap rejected; semantic independence has limits.',
        'training_policy':'One shared model, server CPU only. No automatic activation. Record baseline and compare all frozen sets; backend deterministic safety tests are not counted as model accuracy.'}
    out.mkdir()
    for name,raw in payloads.items():(out/name).write_text(raw)
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'counts':counts,'held_out_count':report['held_out_count']}))


if __name__=='__main__':main()
