"""Combine only declared approved application synthetic SFT sources.
All independent held-out sets stay outside training/validation. No database access.
"""
import argparse,hashlib,json,re,unicodedata
from pathlib import Path
from training_contracts import CLARIFICATION_DESCRIPTION
ROOT=Path(__file__).resolve().parents[2]
SOURCES={'facturation':'facturation-v4-en-fr','management_projet':'management-projet-v1-en-fr'}
parser=argparse.ArgumentParser();parser.add_argument('--include-design-workflow',action='store_true');parser.add_argument('--management-v2',action='store_true');parser.add_argument('--expanded-curriculum',action='store_true');parser.add_argument('--intent-contrasts',action='store_true');parser.add_argument('--refinement',action='store_true');parser.add_argument('--include-contracts',action='store_true');parser.add_argument('--include-gestion-magasin',action='store_true');parser.add_argument('--include-reservation',action='store_true');args=parser.parse_args()
if args.include_design_workflow:SOURCES['design_workflow']='design-workflow-v1-en-fr'
if args.management_v2:
    if not args.include_design_workflow:raise ValueError('The v3 curriculum retains all three approved applications.')
    SOURCES['management_projet']='management-projet-v2-en-fr'
if args.expanded_curriculum:
    if not args.include_design_workflow or not args.management_v2:raise ValueError('Expanded curriculum retains all three approved applications.')
    SOURCES.update(management_projet='management-projet-v3-en-fr',design_workflow='design-workflow-v2-en-fr')
if args.intent_contrasts:
    if not args.expanded_curriculum:raise ValueError('Intent contrasts retain all approved sources and preceding held-outs.')
    SOURCES.update(management_projet='management-projet-v4-en-fr',design_workflow='design-workflow-v3-en-fr')
if args.refinement:
    if not args.intent_contrasts:raise ValueError('Refinement retains the previous complete three-application curriculum.')
    SOURCES.update({app:app.replace('_','-')+'-refinement-v1-en-fr' for app in SOURCES})
if args.include_contracts:
    if not args.intent_contrasts:raise ValueError('Contracts retains all three existing application curricula and their frozen held-outs.')
    SOURCES['contrat']='contracts-v1-en-fr'
if args.include_gestion_magasin:
    if not args.include_contracts:raise ValueError('Gestion Magasin retains the Contracts stage and all earlier application sources.')
    SOURCES['gestion_magasin']='gestion-magasin-v1-en-fr'
if args.include_reservation:
    if not args.include_gestion_magasin:raise ValueError('Reservation retains all preceding application curricula and held-outs.')
    SOURCES['reservation']='reservation-v1-en-fr'
version='shared-v8-en-fr' if args.include_reservation else 'shared-v7-en-fr' if args.include_gestion_magasin else 'shared-v6-en-fr' if args.include_contracts else 'shared-v5-en-fr' if args.intent_contrasts else 'shared-v4-en-fr' if args.expanded_curriculum else 'shared-v3-en-fr' if args.management_v2 else 'shared-v2-en-fr' if args.include_design_workflow else 'shared-v1-en-fr'
if args.refinement:version=version.replace('-en-fr','r2-en-fr')
OUT=ROOT/'training/datasets'/version
SECRET=re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:Bearer\s+)[A-Za-z0-9._-]{16,}|(?:password|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*\S+',re.I)
held={}
for app,source in SOURCES.items():
    dataset={'facturation':'facturation-acceptance-en-fr','management_projet':'management-projet-v1-en-fr','design_workflow':'design-workflow-v1-en-fr','contrat':'contracts-v1-en-fr','gestion_magasin':'gestion-magasin-v1-en-fr','reservation':'reservation-v1-en-fr'}[app]
    path=ROOT/'training/datasets'/dataset/'test.eval.jsonl'
    held[app]=[json.loads(line) for line in path.read_text().splitlines()]
def key(app,prompt):return app+':'+re.sub(r'\W+',' ',unicodedata.normalize('NFKD',prompt).casefold()).strip()
if args.management_v2:
    path=ROOT/'training/datasets/management-projet-v2-en-fr/independent.eval.jsonl'
    held['management_projet'].extend(json.loads(line) for line in path.read_text().splitlines())
if args.expanded_curriculum:
    for app,source in [('management_projet','management-projet-v3-en-fr'),('design_workflow','design-workflow-v2-en-fr')]:
        path=ROOT/'training/datasets'/source/'independent.eval.jsonl'
        held[app].extend(json.loads(line) for line in path.read_text().splitlines())
if args.intent_contrasts:
    for app,source in [('management_projet','management-projet-v4-en-fr'),('design_workflow','design-workflow-v3-en-fr')]:
        path=ROOT/'training/datasets'/source/'independent.eval.jsonl'
        held[app].extend(json.loads(line) for line in path.read_text().splitlines())
if args.refinement:
    for app in ('facturation','management_projet','design_workflow'):
        path=ROOT/'training/datasets'/SOURCES[app]/'independent.eval.jsonl'
        held[app].extend(json.loads(line) for line in path.read_text().splitlines())
held_keys={key(app,row['messages'][-1]['content']) for app,rows in held.items() for row in rows}
counts={};source_hashes={};split_keys={};payloads={}
for name in ['train.jsonl','valid.jsonl']:
    combined=[];keys=set()
    for app,dataset in SOURCES.items():
        path=ROOT/'training/datasets'/dataset/name
        source_hashes[app+'/'+name]=hashlib.sha256(path.read_bytes()).hexdigest()
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if SECRET.search(json.dumps(row,ensure_ascii=False)):raise ValueError('Sensitive source input')
            prompt=next(m['content'] for m in reversed(row['messages']) if m['role']=='user')
            if args.expanded_curriculum:
                for tool in row['tools']:
                    if tool['function']['name']=='clarify':tool['function']['description']=CLARIFICATION_DESCRIPTION
            candidate=key(app,prompt)
            if candidate in keys or candidate in held_keys:raise ValueError('Duplicate or held-out prompt in SFT source')
            keys.add(candidate);combined.append({**row,'application':app})
        counts[app+'/'+name]=len(rows)
    split_keys[name]=keys
    payloads[name]=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in combined)
if split_keys['train.jsonl']&split_keys['valid.jsonl']:raise ValueError('Cross-split prompt overlap')
OUT.mkdir(parents=True,exist_ok=False)
for name,payload in payloads.items():(OUT/name).write_text(payload)
manifest={'version':version.replace('shared-','shared-synthetic-'),'applications':list(SOURCES),'languages':['en','fr'],'source':'Approved versioned synthetic sources only. No confidential business records or conversation data.','sources':source_hashes,'counts':counts,'held_out_exclusion':'All declared independent application acceptance sets excluded by normalized application/prompt key. Per-application near-duplicate limitations remain as stated in their source manifests.','training_policy':'Continue from a separately recorded existing checkpoint. Use complete epochs for v3, covering every source row; record actual steps and exposure. No candidate is automatically activated.','files':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['train.jsonl','valid.jsonl']}}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(counts))
