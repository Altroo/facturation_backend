"""Build versioned synthetic scenarios from a native registry, never business data."""
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from jsonschema import validate
from training_contracts import CLARIFICATION_DESCRIPTION
from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


def prompt_key(row):
    return re.sub(r'\W+', ' ', unicodedata.normalize('NFKD',row['messages'][-1]['content']).casefold()).strip()


class SyntheticCurriculum:
    def __init__(self, application, version, source, registry, shortlist, system, secret, defaults, held_out):
        self.application,self.version,self.registry,self.shortlist,self.system,self.secret,self.defaults = application,version,registry,shortlist,system,secret,defaults
        self.source=ROOT/'training/datasets'/source
        self.output=ROOT/'training/datasets'/version
        self.splits={name:[json.loads(line) for line in (self.source/(name+'.eval.jsonl')).read_text().splitlines()] for name in ['train','valid']}
        self.splits['independent']=[]
        self.held_out=[ROOT/'training/datasets'/path for path in held_out]
        self.clarify={'type':'function','function':{'name':'clarify','description':CLARIFICATION_DESCRIPTION,'parameters':CLARIFICATION_SCHEMA}}

    def refresh_inherited(self, context_transform):
        """Keep semantic labels; bind inherited SFT envelopes to current native permissions."""
        for split in ['train','valid']:
            for row in self.splits[split]:
                context=row.get('trusted_context')
                if context is None:
                    context=json.loads(row['messages'][0]['content'].rsplit('\nTrusted context: ',1)[1])
                context=context_transform(dict(context))
                prompt=row['messages'][-1]['content']
                selected=self.shortlist(prompt,self.registry().permitted(context['capabilities']),context)
                schemas=[t.schema() for t in selected]
                expected=row['expected']
                schema=CLARIFICATION_SCHEMA if expected['tool']=='clarify' else next((t['function']['parameters'] for t in schemas if t['function']['name']==expected['tool']),None)
                if schema is None:raise ValueError('Inherited target is not currently offered: '+row['id'])
                validate(expected['arguments'],schema)
                row.update(trusted_context=context,offered_tools=[t.name for t in selected],offered_tool_schemas=schemas,
                    messages=[{'role':'system','content':self.system+'\nTrusted context: '+json.dumps(context,ensure_ascii=False)}]+[m for m in row['messages'] if m['role']!='system'])

    def add(self, split, key, fr, en, tool, args, context=None, capabilities=None, switch=False):
        for language,prompt in [('fr',fr),('en',en)]:
            trusted={**self.defaults,'application':self.application,'today':'2029-05-23','interface_language':language,**(context or {})}
            if capabilities is not None:trusted['capabilities']=list(capabilities)
            if switch:trusted['interface_language']='en' if language=='fr' else 'fr'
            selected=self.shortlist(prompt,self.registry().permitted(trusted['capabilities']),trusted)
            schemas=[t.schema() for t in selected]
            expected={'tool':tool,'arguments':{**args,**({'language':language} if tool=='clarify' else {})}}
            schema=CLARIFICATION_SCHEMA if tool=='clarify' else next((t['function']['parameters'] for t in schemas if t['function']['name']==tool),None)
            if schema is None:raise ValueError('Expected tool absent from actual native shortlist: '+key)
            validate(expected['arguments'],schema)
            messages=[{'role':'system','content':self.system+'\nTrusted context: '+json.dumps(trusted,ensure_ascii=False)}]
            if switch:messages.append({'role':'user','content':'Hello' if language=='fr' else 'Bonjour'})
            messages.append({'role':'user','content':prompt})
            self.splits[split].append({'id':self.version+'-'+key+'-'+language,'category':key.split('-')[0],
                'language':language,'trusted_context':trusted,'messages':messages,'expected':expected,
                'offered_tools':[t.name for t in selected],'offered_tool_schemas':schemas})

    def write(self, generator, metadata):
        groups=[]
        for name,rows in self.splits.items():
            keys={prompt_key(row) for row in rows}
            if len(keys)!=len(rows):raise ValueError('Duplicate prompt within '+name+' split')
            groups.append(keys)
        held=[json.loads(line) for path in self.held_out for line in path.read_text().splitlines()]
        groups.append({prompt_key(row) for row in held})
        if any(groups[i]&groups[j] for i in range(len(groups)) for j in range(i+1,len(groups))):raise ValueError('Cross-split or frozen prompt overlap')
        rows=[row for split in self.splits.values() for row in split]
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate scenario identifier')
        if any(self.secret.search(json.dumps(row,ensure_ascii=False)) for row in rows):raise ValueError('Sensitive input')
        self.output.mkdir(exist_ok=False)
        def write(name, rows):
            (self.output/name).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
        for name,rows in self.splits.items():write(name+'.eval.jsonl',rows)
        for name in ['train','valid']:
            write(name+'.jsonl',[{'messages':row['messages']+[{'role':'assistant','content':None,'tool_calls':[{'type':'function','function':{'name':row['expected']['tool'],'arguments':row['expected']['arguments']}}]}],
                'tools':row['offered_tool_schemas']+[self.clarify]} for row in self.splits[name]])
        manifest={'version':self.version,'application':self.application,'languages':['en','fr'],
            'source':'Actual native registry/planner and reviewed form/status metadata. Synthetic scenarios only; database queries forbidden.',
            'source_dataset':self.source.name,'source_manifest_sha256':hashlib.sha256((self.source/'manifest.json').read_bytes()).hexdigest(),
            'generator_sha256':hashlib.sha256(Path(generator).read_bytes()).hexdigest(),
            'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'native_metadata_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in metadata},
            'counts':{name:len(rows) for name,rows in self.splits.items()},
            'categories':dict(Counter(row['category'] for row in self.splits['train'])),
            'frozen_sets':{p.parent.name+'/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.held_out},
            'split_policy':'Bilingual pairs remain together. All old frozen acceptance/companion prompts excluded by normalized exact key. New independent labels never enter SFT or validation. Failure categories informed adaptation; old tests are regressions. Semantic similarity is not exhaustively excluded.',
            'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.glob('*.jsonl')}}
        (self.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({'dataset':self.version,'counts':manifest['counts']}),flush=True)
