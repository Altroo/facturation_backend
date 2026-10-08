"""Active English/French dataset. Historical v1/v2 evidence remains immutable."""
import hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from chat_ai_assistant.orchestrator import SYSTEM
from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
from chat_ai_assistant.contracts import ChatAITool
from chat_ai_assistant.routing import shortlist
from jsonschema import Draft202012Validator
import build_dataset_v2 as historical
LANGS=['en','fr']
TRAIN,VALID,TEST=historical.TRAIN,historical.VALID,historical.TEST

def main():
    directory=ROOT/'training/datasets/facturation-v3-en-fr'
    directory.mkdir(exist_ok=True)
    previous=ROOT/'training/datasets/facturation-v2/tool-schemas.json'
    target=directory/'tool-schemas.json'
    if not target.exists():target.write_bytes(previous.read_bytes())
    schema_path=directory/'tool-schemas.json'
    schemas=json.loads(schema_path.read_text())
    schema_map={item['function']['name']:item['function']['parameters'] for item in schemas}
    tools=[ChatAITool(item['function']['name'],item['function']['description'],item['function']['parameters'],{},item['function']['name']) for item in schemas]
    clarify={'type':'function','function':{'name':'clarify','description':'Ask for missing details, ambiguous financial metric, or unsupported request. Use the CURRENT message language.', 'parameters':CLARIFICATION_SCHEMA}}
    files=[];seen={};router_failures=[]
    for split,groups in [('train',TRAIN),('valid',VALID),('test',TEST)]:
        rows=[];evals=[]
        for index,(category,tool,arguments,texts) in enumerate(groups):
            for language,text in zip(LANGS,texts):
                normalized=re.sub(r'\W','',text.casefold())
                if normalized in seen:raise ValueError(f'Duplicate across scenarios {seen[normalized]} / {split}-{index}')
                seen[normalized]=f'{split}-{index}'
                if re.search(r'BEGIN.*PRIVATE KEY|Bearer\s+\S+|(?:password|api_key)\s*[:=]',text,re.I):raise ValueError('Sensitive-pattern check failed')
                args=dict(arguments)
                if tool=='clarify':
                    args={'reason':args.get('reason',{'ambiguity':'ambiguous_metric','missing_year':'missing_details'}.get(category,'unsupported')),'language':language}
                if tool=='knowledge':args={'query':text}
                Draft202012Validator(CLARIFICATION_SCHEMA if tool=='clarify' else schema_map[tool]).validate(args)
                context={'application':'facturation','today':'2026-10-08','currency_default':'MAD'}
                if category in ('current','related'):context['current_invoice_id']=47
                if category in ('multi_turn','previous_open','previous'):
                    context.update(previous_result_type='invoice',previous_result_count=3)
                messages=[{'role':'system','content':SYSTEM+'\nTrusted context: '+json.dumps(context,ensure_ascii=False)}]
                if category=='language_switch':messages.append({'role':'user','content':'Show me unpaid invoices.' if language!='en' else 'Affiche les factures impayées.'})
                messages.append({'role':'user','content':text})
                offered=shortlist(text,tools,context)
                if tool!='clarify' and tool not in {item.name for item in offered}:
                    router_failures.append(f'{split}-{index}-{language}:{tool}')
                assistant={'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':tool,'arguments':args}}]}
                rows.append({'messages':messages+[assistant],'tools':[item.schema() for item in offered]+[clarify]})
                evals.append({'id':f'{split}-{index:02}-{language}','group':f'{split}-{index:02}','category':category,'language':language,'messages':messages,'offered_tools':[item.name for item in offered],'expected':{'tool':tool,'arguments':args}})
        for suffix,values in [('.jsonl',rows),('.eval.jsonl',evals)]:
            path=directory/(split+suffix)
            data=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values)
            if path.exists() and path.read_text()!=data:raise ValueError('Version already differs; create a new dataset version.')
            path.write_text(data)
            files.append({'file':path.name,'rows':len(values),'sha256':hashlib.sha256(data.encode()).hexdigest()})
    report={'version':'facturation-synthetic-v3-en-fr','languages':LANGS,'source':'Verified tool schemas and synthetic English/French scenarios; no database records or private conversations',
            'split_policy':'Both English/French phrasings in one scenario split. Entity and combination variations; small pilot, not independent population evidence. No evaluation results used for training.',
            'schema_sha256':hashlib.sha256(schema_path.read_bytes()).hexdigest(),'router_omitted_expected_tools':router_failures,
            'label_policy':'User prompts use visible form labels; technical names exist only inside structured tool calls.', 'files':files}
    (directory/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
