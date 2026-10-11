"""Reproducible EN/FR consolidation curriculum from approved native contracts.
No database queries, model inference, private records or frozen-label corrections.
Prior evaluations are retained regressions; new independent cases stay out of SFT.
"""
import argparse, copy, hashlib, json, os, re, sys, unicodedata
from pathlib import Path
from jsonschema import validate
from training_contracts import CLARIFICATION_DESCRIPTION
from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
ROOT=Path(__file__).resolve().parents[2]
SOURCES={'management_projet':'management-projet-v4-en-fr','design_workflow':'design-workflow-v3-en-fr','facturation':'facturation-v4-en-fr'}
FROZEN={'management_projet':['management-projet-v1-en-fr/test.eval.jsonl','management-projet-v2-en-fr/independent.eval.jsonl','management-projet-v3-en-fr/independent.eval.jsonl','management-projet-v4-en-fr/independent.eval.jsonl'],
'design_workflow':['design-workflow-v1-en-fr/test.eval.jsonl','design-workflow-v2-en-fr/independent.eval.jsonl','design-workflow-v3-en-fr/independent.eval.jsonl'],
'facturation':['facturation-acceptance-en-fr/test.eval.jsonl']}

def key(text):return re.sub(r'\W+',' ',unicodedata.normalize('NFKD',text).casefold()).strip()

def main():
 p=argparse.ArgumentParser();p.add_argument('--application',choices=SOURCES,required=True);p.add_argument('--backend',type=Path,required=True);a=p.parse_args()
 app=a.application;source=ROOT/'training/datasets'/SOURCES[app];out=ROOT/'training/datasets'/(app.replace('_','-')+'-refinement-v1-en-fr')
 if out.exists():raise ValueError('Never overwrite a frozen dataset version')
 sys.path.insert(0,str(a.backend))
 os.environ.setdefault('DJANGO_SETTINGS_MODULE',app+'_backend.settings_ai_test' if app=='facturation' else app+'_backend.settings_test')
 from django.db.backends.base.base import BaseDatabaseWrapper
 def forbidden(*args,**kwargs):raise RuntimeError('Dataset generation must not connect to databases')
 BaseDatabaseWrapper.ensure_connection=forbidden
 import django;django.setup()
 from chat_ai.tools import registry
 if app=='facturation':
  from chat_ai_assistant.orchestrator import SYSTEM
  from chat_ai_assistant.routing import shortlist
  from build_dataset_v4 import PROFILES,validate_business_action
  default_caps=PROFILES['member_edit']
 else:
  from chat_ai.planner import SYSTEM,shortlist
  default_caps=['read','print','create','update','delete'] if app=='management_projet' else ['read','create','update','archive','mutate','report']
 splits={s:[json.loads(x) for x in (source/(s+'.eval.jsonl')).read_text().splitlines()] for s in ('train','valid')};splits['independent']=[]
 def add(split,name,fr,en,tool,args,context=None,caps=None,history=None):
  for language,text in [('fr',fr),('en',en)]:
   trusted={'application':app,'today':'2031-07-16','interface_language':language,'previous_result_type':None,'previous_result_count':0}
   if app=='facturation':trusted.update(currency_default='MAD',current_invoice_id=None)
   elif app=='management_projet':trusted.update(currency_default='MAD',capabilities=caps or default_caps)
   else:trusted.update(capabilities=caps or default_caps,current_resource=None,current_identifier=None,previous_result_identifiers=[])
   trusted.update(context or {})
   selected=shortlist(text,registry().permitted(caps or default_caps),trusted);schemas=[t.schema() for t in selected]
   expected={'tool':tool,'arguments':{**args,**({'language':language} if tool=='clarify' else {})}}
   schema=CLARIFICATION_SCHEMA if tool=='clarify' else next((s['function']['parameters'] for s in schemas if s['function']['name']==tool),None)
   if schema is None:raise ValueError('Native shortlist omitted '+tool+': '+name)
   validate(expected['arguments'],schema)
   if app=='facturation':validate_business_action(tool,expected['arguments'],trusted,text)
   if app=='management_projet' and tool=='prepare_change':
    from chat_ai.targets import trusted_target
    from datetime import datetime,timezone
    assert trusted_target(args['resource'],args['identifier'],instruction=text,context={'resource':trusted.get('current_resource'),'identifier':trusted.get('current_identifier')},state={},now=datetime.now(timezone.utc)),name
   messages=[{'role':'system','content':SYSTEM+'\nTrusted context: '+json.dumps(trusted,ensure_ascii=False)}]
   if history:messages.extend({'role':'user','content':pair[0 if language=='fr' else 1]} for pair in history)
   messages.append({'role':'user','content':text})
   splits[split].append({'id':app+'-refinement-v1-'+name+'-'+language,'category':name.split('-')[0],'language':language,'trusted_context':trusted,'messages':messages,'expected':expected,'offered_tools':[t.name for t in selected],'offered_tool_schemas':schemas})
 scenarios(app,add)
 # Revalidate every inherited action against its original permission-narrowed envelope.
 clarify={'type':'function','function':{'name':'clarify','description':CLARIFICATION_DESCRIPTION,'parameters':CLARIFICATION_SCHEMA}}
 groups=[];ids=set()
 for split,rows in splits.items():
  prompts=set()
  for row in rows:
   prompt=row['messages'][-1]['content'];k=key(prompt)
   if k in prompts:raise ValueError('Duplicate prompt within '+split+': '+row['id'])
   prompts.add(k)
   if row['id'] in ids:raise ValueError('Duplicate id')
   ids.add(row['id'])
   expected=row['expected'];schema=CLARIFICATION_SCHEMA if expected['tool']=='clarify' else next(s['function']['parameters'] for s in row['offered_tool_schemas'] if s['function']['name']==expected['tool'])
   validate(expected['arguments'],schema)
   content=json.dumps(row,ensure_ascii=False)
   if re.search(r'[\u0600-\u06ff]|BEGIN.*PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret|token)\s*[:=]',content,re.I):raise ValueError('Language or sensitive-data violation')
  groups.append(prompts)
 frozen_paths=[ROOT/'training/datasets'/n for n in FROZEN[app]]
 groups.append({key(json.loads(line)['messages'][-1]['content']) for f in frozen_paths for line in f.read_text().splitlines()})
 if any(groups[i]&groups[j] for i in range(len(groups)) for j in range(i+1,len(groups))):raise ValueError('Cross-split or frozen prompt collision')
 payloads={}
 for split,rows in splits.items():
  payloads[split+'.eval.jsonl']=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows)
  if split!='independent':payloads[split+'.jsonl']=''.join(json.dumps({'messages':row['messages']+[{'role':'assistant','content':None,'tool_calls':[{'type':'function','function':{'name':row['expected']['tool'],'arguments':row['expected']['arguments']}}]}],'tools':row['offered_tool_schemas']+[clarify]},ensure_ascii=False)+'\n' for row in rows)
 metadata={'version':out.name,'application':app,'languages':['en','fr'],'counts':{s:len(r) for s,r in splits.items()},'source_dataset':source.name,'source_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'files':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in payloads.items()},'frozen_sets':{str(f.relative_to(ROOT/'training/datasets')):hashlib.sha256(f.read_bytes()).hexdigest() for f in frozen_paths},'split_policy':'Distinct authored bilingual scenarios. Old frozen failures informed categories, not copied labels. Old sets are regression evidence; new independent cases never enter train or validation. Exact normalized overlaps rejected; semantic similarities remain possible.','source':'Native permission-narrowed registries and verified fields. Synthetic entities only; all database connections forbidden.'}
 native=Path(__import__('chat_ai.tools',fromlist=['x']).__file__)
 metadata['native_tools_sha256']=hashlib.sha256(native.read_bytes()).hexdigest()
 out.mkdir()
 for n,v in payloads.items():(out/n).write_text(v)
 (out/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
 print(json.dumps({'dataset':out.name,'counts':metadata['counts']}))

def scenarios(app,add):
 if app=='design_workflow':
  rows=[
   ('archive-project','Cherche le projet archivé nommé Canopée Démo.','Look up the archived project called Canopée Démo.','search_records',{'resource':'project','project_name':'Canopée Démo','archived':True}),
   ('archive-project-name','Dans les archives des projets, retrouve Belvédère Test.','Within archived projects, find Belvédère Test.','search_records',{'resource':'project','project_name':'Belvédère Test','archived':True}),
   ('active-project','Retrouve le projet Canopée Démo parmi les projets non archivés.','Find project Canopée Démo among unarchived projects.','search_records',{'resource':'project','project_name':'Canopée Démo','archived':False}),
   ('archive-task','Retrouve les cartes archivées nommées Maquette dans Canopée Démo.','Find archived cards named Maquette in Canopée Démo.','search_records',{'resource':'task','query':'Maquette','project_name':'Canopée Démo','archived':True}),
   ('assigned-project','Pour Canopée Démo, les cartes de Démo Salma.','For Canopée Démo, the cards assigned to Démo Salma.','search_records',{'resource':'task','project_name':'Canopée Démo','assignee_name':'Démo Salma'}),
   ('assigned-review','Tâches en revue attribuées à Démo Salma dans Belvédère Test.','Tasks in review assigned to Démo Salma in Belvédère Test.','search_records',{'resource':'task','project_name':'Belvédère Test','assignee_name':'Démo Salma','status':'in_review'}),
   ('assigned-blocked','Dans Canopée Démo, affiche les tâches bloquées de Démo Sami.','In Canopée Démo, show blocked tasks assigned to Démo Sami.','search_records',{'resource':'task','project_name':'Canopée Démo','assignee_name':'Démo Sami','status':'blocked'}),
   ('query-person','Retrouve les cartes dont le texte contient « Démo Sami ».','Find cards whose text contains “Démo Sami”.','search_records',{'resource':'task','query':'Démo Sami'}),
   ('assigned-query','Cartes attribuées à Démo Sami contenant « Façade » dans Belvédère Test.','Cards assigned to Démo Sami containing “Façade” in Belvédère Test.','search_records',{'resource':'task','assignee_name':'Démo Sami','query':'Façade','project_name':'Belvédère Test'}),
   ('review-state','Cartes du projet Belvédère Test à l’état En revue.','Cards of project Belvédère Test in the In Review state.','search_records',{'resource':'task','project_name':'Belvédère Test','status':'in_review'}),
   ('todo-state','Mes cartes à faire sur Canopée Démo.','My to-do cards on Canopée Démo.','search_records',{'resource':'task','project_name':'Canopée Démo','status':'todo','mine':True}),
   ('missing-year','Combien de minutes sur Canopée Démo pendant septembre ?','How many minutes on Canopée Démo during September?','clarify',{'reason':'missing_details'}),
   ('missing-year-report','Le rapport de juillet pour les heures de Belvédère Test.','The July working-hours report for Belvédère Test.','clarify',{'reason':'missing_details'}),
   ('missing-year-range','Heures enregistrées du 7 mars au 19 mars pour Canopée Démo.','Hours recorded from March 7 to March 19 for Canopée Démo.','clarify',{'reason':'missing_details'}),
   ('explicit-month','Temps enregistré en septembre 2031 sur Canopée Démo.','Time recorded in September 2031 on Canopée Démo.','time_report',{'project_name':'Canopée Démo','date_from':'2031-09-01','date_to':'2031-09-30'}),
   ('explicit-range','Minutes de Belvédère Test entre le 2032-07-08 et le 2032-07-27.','Belvédère Test minutes between 2032-07-08 and 2032-07-27.','time_report',{'project_name':'Belvédère Test','date_from':'2032-07-08','date_to':'2032-07-27'}),
   ('workload-contrast','Nombre de cartes de Canopée Démo par statut.','Number of Canopée Démo cards by status.','workload_summary',{'project_name':'Canopée Démo'}),
   ('unsupported-person','Temps total passé uniquement par Démo Sami dans Canopée Démo.','Total time spent only by Démo Sami in Canopée Démo.','clarify',{'reason':'unsupported'}),
  ]
  for name,fr,en,tool,args in rows:add('train',name,fr,en,tool,args)
  add('train','history-year','Pour novembre, combien de temps ?','For November, how much time?','clarify',{'reason':'missing_details'},history=[('Temps enregistré pour Canopée Démo.','Recorded time for Canopée Démo.')])
  add('train','denied-report','Rapport du temps de Canopée Démo.','Time report for Canopée Démo.','clarify',{'reason':'unsupported'},caps=['read'])
  for split,name,fr,en,tool,args in [
   ('valid','archive-composition','Recherche les projets archivés dont le nom est Lucarne Essai.','Search archived projects whose name is Lucarne Essai.','search_records',{'resource':'project','project_name':'Lucarne Essai','archived':True}),
   ('valid','date-question','Tu peux me donner les heures de juin sur Lucarne Essai ?','Could you give me the June hours on Lucarne Essai?','clarify',{'reason':'missing_details'}),
   ('valid','assigned-status','Dans Lucarne Essai, les cartes en cours de Démo Aya.','In Lucarne Essai, in-progress cards assigned to Démo Aya.','search_records',{'resource':'task','project_name':'Lucarne Essai','assignee_name':'Démo Aya','status':'in_progress'}),
   ('independent','archive-limited','J’ai besoin de deux projets archivés au maximum, nom Pavillon Synthétique.','I need at most two archived projects, name Pavillon Synthétique.','search_records',{'resource':'project','project_name':'Pavillon Synthétique','archived':True,'limit':2}),
   ('independent','assigned-late','Sur Pavillon Synthétique, quelles cartes de Démo Farah sont en retard ?','On Pavillon Synthétique, which cards assigned to Démo Farah are overdue?','search_records',{'resource':'task','project_name':'Pavillon Synthétique','assignee_name':'Démo Farah','overdue':True}),
   ('independent','year-implicit','J’aimerais connaître les minutes travaillées en octobre.','I would like to know the minutes worked in October.','clarify',{'reason':'missing_details'}),
   ('independent','explicit-date','En février 2036, quel temps de travail sur Pavillon Synthétique ?','In February 2036, what working time on Pavillon Synthétique?','time_report',{'project_name':'Pavillon Synthétique','date_from':'2036-02-01','date_to':'2036-02-29'}),
   ('independent','review-mine','Parmi mes cartes de Pavillon Synthétique, celles en revue seulement.','Among my Pavillon Synthétique cards, only those in review.','search_records',{'resource':'task','project_name':'Pavillon Synthétique','mine':True,'status':'in_review'}),
  ]:add(split,name,fr,en,tool,args)
 elif app=='management_projet':
  management(add)
 else:
  facturation(add)

def management(add):
 rows=[
  ('budget-stage','Recherche les écritures du budget réel de Canopée Démo, rubrique Menuiserie.','Search actual-budget entries of Canopée Démo, section Menuiserie.','search_records',{'resource':'budget_entry','project_name':'Canopée Démo','query':'Menuiserie'}),
  ('budget-fragment','Budget réel : Belvédère Test ; étape Électricité.','Actual budget: Belvédère Test; stage Électricité.','search_records',{'resource':'budget_entry','project_name':'Belvédère Test','query':'Électricité'}),
  ('budget-rows','Lignes de budget réel qui parlent de Vitrage dans Canopée Démo.','Actual-budget rows mentioning Vitrage in Canopée Démo.','search_records',{'resource':'budget_entry','project_name':'Canopée Démo','query':'Vitrage'}),
  ('budget-summary','Montant du budget prévu de Canopée Démo.','Planned budget amount for Canopée Démo.','financial_summary',{'metric':'budget','project_name':'Canopée Démo'}),
  ('records-three','Dépenses de Belvédère Test pour le client Démo Salma chez le fournisseur Fictif Vitrage.','Expenses of Belvédère Test for customer Démo Salma from supplier Fictif Vitrage.','search_records',{'resource':'expense','project_name':'Belvédère Test','client_name':'Démo Salma','supplier_name':'Fictif Vitrage'}),
  ('records-phrase','Pour Canopée Démo, retrouve les échéances dues au plus tard le 2031-09-14.','For Canopée Démo, find payment schedules due no later than 2031-09-14.','search_records',{'resource':'payment_schedule','project_name':'Canopée Démo','date_to':'2031-09-14'}),
  ('records-full','Dépenses contenant « chêne », projet Canopée Démo, client Démo Sami, fournisseur Fictif Bois, du 2031-02-01 au 2031-02-16.','Expenses containing “chêne”, project Canopée Démo, customer Démo Sami, supplier Fictif Bois, from 2031-02-01 to 2031-02-16.','search_records',{'resource':'expense','query':'chêne','project_name':'Canopée Démo','client_name':'Démo Sami','supplier_name':'Fictif Bois','date_from':'2031-02-01','date_to':'2031-02-16'}),
  ('search-before-edit','/modifier le projet associé au client Démo Salma.','/edit the project associated with customer Démo Salma.','search_records',{'resource':'project','client_name':'Démo Salma'}),
  ('search-before-delete','/supprimer le devis du fournisseur Fictif Vitrage sur Belvédère Test.','/delete the quote from supplier Fictif Vitrage on Belvédère Test.','search_records',{'resource':'quote','supplier_name':'Fictif Vitrage','project_name':'Belvédère Test'}),
  ('quote-business','Supprime le devis numéro 0731/31 une fois la fiche choisie.','Delete quote number 0731/31 once its record is selected.','search_records',{'resource':'quote','query':'0731/31'}),
  ('quote-business-edit','Modifie la remarque du devis 0426/32.','Edit the remark of quote 0426/32.','search_records',{'resource':'quote','query':'0426/32'}),
  ('explicit-client','Modifie le client ID 2074 : Ville « Oujda ».','Edit customer ID 2074: City “Oujda”.','prepare_change',{'resource':'client','identifier':2074,'operation':'update','changes':{'ville':'Oujda'}}),
  ('explicit-client-label','Change la ville du client identifiant 2075 en « Fès ».','Change the city of customer ID 2075 to “Fès”.','prepare_change',{'resource':'client','identifier':2075,'operation':'update','changes':{'ville':'Fès'}}),
  ('explicit-delete','/supprimer le devis identifiant 2076 après confirmation.','/delete quote ID 2076 after confirmation.','prepare_change',{'resource':'quote','identifier':2076,'operation':'delete'}),
  ('ambiguous-earned','Combien avons-nous gagné sur Canopée Démo ce mois-ci ?','How much did we earn on Canopée Démo this month?','clarify',{'reason':'ambiguous_metric'}),
  ('ambiguous-money','On a fait combien d’argent avec Belvédère Test ?','How much money did we make with Belvédère Test?','clarify',{'reason':'ambiguous_metric'}),
  ('explicit-receipts','Total encaissé pour Belvédère Test pendant le mois précédent.','Total receipts for Belvédère Test during the previous month.','financial_summary',{'metric':'revenue','project_name':'Belvédère Test','period':'previous_month'}),
  ('unsupported-supplier','Somme des dépenses chez Fictif Bois pour Canopée Démo.','Sum of expenses from Fictif Bois for Canopée Démo.','clarify',{'reason':'unsupported'}),
  ('supplier-records','Liste les dépenses chez Fictif Bois pour Canopée Démo.','List expenses from Fictif Bois for Canopée Démo.','search_records',{'resource':'expense','supplier_name':'Fictif Bois','project_name':'Canopée Démo'}),
  ('missing-year-receipts','Encaissements de septembre dans Belvédère Test.','September receipts in Belvédère Test.','clarify',{'reason':'missing_details'}),
  ('missing-year-expenses','Retrouve les dépenses de juin sur Canopée Démo.','Find June expenses on Canopée Démo.','clarify',{'reason':'missing_details'}),
  ('missing-year-range','Dépenses du 2 février au 11 février.','Expense records from February 2 to February 11.','clarify',{'reason':'missing_details'}),
  ('explicit-year','Retrouve les encaissements de septembre 2031 sur Belvédère Test.','Find September 2031 receipts on Belvédère Test.','search_records',{'resource':'revenue','project_name':'Belvédère Test','date_from':'2031-09-01','date_to':'2031-09-30'}),
 ]
 for name,fr,en,tool,args in rows:add('train',name,fr,en,tool,args)
 add('train','revoked-edit','Modifie la ville du client ID 2080 en « Oujda ».','Change customer ID 2080 city to “Oujda”.','clarify',{'reason':'unsupported'},caps=['read'])
 for split,name,fr,en,tool,args in [
  ('valid','budget-description','Pour Lucarne Essai, budget réel avec « Maçonnerie ».','For Lucarne Essai, actual-budget entries with “Maçonnerie”.','search_records',{'resource':'budget_entry','project_name':'Lucarne Essai','query':'Maçonnerie'}),
  ('valid','year-unsaid','Les devis de février pour le client Démo Aya.','February quotes for customer Démo Aya.','clarify',{'reason':'missing_details'}),
  ('valid','edit-identified','Pour la fiche du client identifiant 2151, propose de modifier ces coordonnées : Adresse « Rue témoin 4 », Ville « Meknès ».','For customer ID 2151, propose an update to these contact details: Address “Rue témoin 4”, City “Meknès”.','prepare_change',{'resource':'client','identifier':2151,'operation':'update','changes':{'adresse':'Rue témoin 4','ville':'Meknès'}}),
  ('independent','budget-dated','Pour Pavillon Synthétique, cherche Étanchéité dans le budget réel depuis le 2036-02-01.','For Pavillon Synthétique, find Étanchéité in actual-budget entries since 2036-02-01.','search_records',{'resource':'budget_entry','project_name':'Pavillon Synthétique','query':'Étanchéité','date_from':'2036-02-01'}),
  ('independent','business-number','/modifier le devis portant le numéro 0582/36.','/edit the quote bearing number 0582/36.','search_records',{'resource':'quote','query':'0582/36'}),
  ('independent','supplier-record-limit','Deux dépenses au maximum du fournisseur Fictif Pierre pour Pavillon Synthétique.','At most two expenses from supplier Fictif Pierre for Pavillon Synthétique.','search_records',{'resource':'expense','project_name':'Pavillon Synthétique','supplier_name':'Fictif Pierre','limit':2}),
  ('independent','unsupported-total','Quel montant cumulé a été dépensé chez Fictif Pierre ?','What cumulative amount was spent with Fictif Pierre?','clarify',{'reason':'unsupported'}),
  ('independent','month-implicit','Peux-tu afficher les échéances de novembre ?','Can you display the November payment schedules?','clarify',{'reason':'missing_details'}),
  ('independent','label-edit','Pour le client identifiant 2301, change Ville en « Essaouira ».','For customer ID 2301, change City to “Essaouira”.','prepare_change',{'resource':'client','identifier':2301,'operation':'update','changes':{'ville':'Essaouira'}}),
 ]:add(split,name,fr,en,tool,args)

def facturation(add):
 rows=[
  ('invoice-all','Au maximum deux factures impayées du client SYN-Galene contenant SYN-BOULON, du 2031-03-04 au 2031-03-21.','At most two unpaid invoices for customer SYN-Galene containing SYN-BOULON, from 2031-03-04 to 2031-03-21.','search_invoices',{'client_name':'SYN-Galene','product_name':'SYN-BOULON','unpaid':True,'date_from':'2031-03-04','date_to':'2031-03-21','limit':2}),
  ('invoice-all-natural','Je cherche trois factures maximum pour SYN-Amarante, avec SYN-LATTE et un reste à payer, émises entre le 5 juin 2032 et le 18 juin 2032.','I need no more than three invoices for SYN-Amarante, with SYN-LATTE and an outstanding balance, issued between June 5, 2032 and June 18, 2032.','search_invoices',{'client_name':'SYN-Amarante','product_name':'SYN-LATTE','unpaid':True,'date_from':'2032-06-05','date_to':'2032-06-18','limit':3}),
  ('client-name','Retrouve le client nommé SYN-Galene.','Look up the customer named SYN-Galene.','search_clients',{'query':'SYN-Galene'}),
  ('payment-all','Règlements valides de la facture 0438/31 pour SYN-Galene contenant SYN-BOULON, du 2031-03-04 au 2031-03-21.','Valid payments for invoice 0438/31 for SYN-Galene containing SYN-BOULON, from 2031-03-04 to 2031-03-21.','search_payments',{'invoice_number':'0438/31','client_name':'SYN-Galene','product_name':'SYN-BOULON','status':'Valide','date_from':'2031-03-04','date_to':'2031-03-21'}),
  ('payment-cancelled','Règlements annulés pour SYN-Amarante en juin 2032.','Cancelled payments for SYN-Amarante in June 2032.','search_payments',{'client_name':'SYN-Amarante','status':'Annulé','date_from':'2032-06-01','date_to':'2032-06-30'}),
  ('payment-valid','Liste les paiements au statut Valide liés à la facture 0570/32.','List payments with status Valide linked to invoice 0570/32.','search_payments',{'invoice_number':'0570/32','status':'Valide'}),
  ('stock-reference','Stock au minimum, référence SYN-REF-213, emplacement SYN-Zone-Delta.','Minimum stock, reference SYN-REF-213, location SYN-Zone-Delta.','search_operations',{'resource':'stock_balance','reference':'SYN-REF-213','location_name':'SYN-Zone-Delta','status':'minimum'}),
  ('stock-product','Stock au minimum, produit SYN-BOULON, emplacement SYN-Zone-Delta.','Minimum stock, product SYN-BOULON, location SYN-Zone-Delta.','search_operations',{'resource':'stock_balance','product_name':'SYN-BOULON','location_name':'SYN-Zone-Delta','status':'minimum'}),
  ('inventory-draft','Inventaires Brouillon dans SYN-Zone-Delta pendant juin 2032.','Draft inventories in SYN-Zone-Delta during June 2032.','search_operations',{'resource':'stock_inventory','location_name':'SYN-Zone-Delta','status':'draft','date_from':'2032-06-01','date_to':'2032-06-30'}),
  ('logistics-all','Dossiers logistiques en Transit du fournisseur SYN-Verre pour le client SYN-Galene avec le produit SYN-BOULON.','Logistics orders in Transit from supplier SYN-Verre for customer SYN-Galene with product SYN-BOULON.','search_operations',{'resource':'logistics_order','supplier_name':'SYN-Verre','client_name':'SYN-Galene','product_name':'SYN-BOULON','status':'Transit'}),
  ('invoice-edit-date','Sur la facture 0438/31, mets Date échéance au 24 août 2031 et Termes de paiement à « 30 jours ».','On invoice 0438/31, set Due date to August 24, 2031 and Payment terms to “30 jours”.','prepare_change',{'resource':'invoice','invoice_number':'0438/31','operation':'update','changes':{'date_echeance':'2031-08-24','termes_paiement':'30 jours'}}),
  ('invoice-edit-date-only','Modifie la Date échéance de la facture 0570/32 au 3 septembre 2032.','Edit the Due date of invoice 0570/32 to September 3, 2032.','prepare_change',{'resource':'invoice','invoice_number':'0570/32','operation':'update','changes':{'date_echeance':'2032-09-03'}}),
  ('missing-year','Factures de septembre pour SYN-Galene.','September invoices for SYN-Galene.','clarify',{'reason':'missing_details'}),
  ('missing-year-quote','Les devis de février contenant SYN-BOULON.','February quotes containing SYN-BOULON.','clarify',{'reason':'missing_details'}),
  ('missing-year-range','Factures du 6 juin au 13 juin pour SYN-Amarante.','Invoices from June 6 to June 13 for SYN-Amarante.','clarify',{'reason':'missing_details'}),
  ('explicit-year-invoices','Factures de septembre 2031 pour SYN-Galene.','September 2031 invoices for SYN-Galene.','search_invoices',{'client_name':'SYN-Galene','date_from':'2031-09-01','date_to':'2031-09-30'}),
  ('unsupported-stock-write','Mets la quantité du stock SYN-BOULON à 8.','Set stock quantity of SYN-BOULON to 8.','clarify',{'reason':'unsupported'}),
  ('unsupported-payment-write','Supprime le règlement de la facture 0438/31.','Delete the payment of invoice 0438/31.','clarify',{'reason':'unsupported'}),
 ]
 for name,fr,en,tool,args in rows:add('train',name,fr,en,tool,args)
 add('train','delivery-relative','Bons de livraison de SYN-Galene avec SYN-BOULON, depuis le premier jour du mois dernier jusqu’à hier.','Delivery notes for SYN-Galene with SYN-BOULON, from the first day of last month through yesterday.','search_documents',{'resource':'delivery_note','client_name':'SYN-Galene','product_name':'SYN-BOULON','date_from':'2031-06-01','date_to':'2031-07-15'})
 add('train','quote-relative','Devis de SYN-Amarante depuis le début de cette année jusqu’à hier.','Quotes for SYN-Amarante from the beginning of this year through yesterday.','search_quotes',{'client_name':'SYN-Amarante','date_from':'2031-01-01','date_to':'2031-07-15'})
 add('train','history-unpaid','Dans ces résultats, garde uniquement les impayées.','Within these results, keep only unpaid ones.','previous_results',{'operation':'unpaid'},context={'previous_result_type':'invoice','previous_result_count':4},history=[('Les factures de SYN-Galene du 2031-03-04 au 2031-03-21.','Invoices for SYN-Galene from 2031-03-04 to 2031-03-21.')])
 add('train','history-articles','Réaffiche les articles que tu viens de trouver.','Show again the articles you just found.','previous_results',{'operation':'show'},context={'previous_result_type':'article','previous_result_count':3},history=[('Cherche les articles avec SYN-BOULON.','Find articles with SYN-BOULON.')])
 add('train','history-articles-switch','Remontre ces articles, s’il te plaît.','Show those articles again, please.','previous_results',{'operation':'show'},context={'previous_result_type':'article','previous_result_count':2},history=[('Search articles by reference SYN-REF-213.','Recherche les articles par référence SYN-REF-213.')])
 add('train','history-date-switch','Montre les factures de juillet pour SYN-Galene.','Show July invoices for SYN-Galene.','clarify',{'reason':'missing_details'},history=[('Hello, I need an invoice.','Bonjour, je cherche une facture.')])
 for split,name,fr,en,tool,args in [
  ('valid','invoice-combined','Quatre factures non soldées maximum, client SYN-Tilleul, produit SYN-CABLE, datées du 2033-01-07 au 2033-01-19.','At most four unpaid invoices, customer SYN-Tilleul, product SYN-CABLE, dated from 2033-01-07 to 2033-01-19.','search_invoices',{'client_name':'SYN-Tilleul','product_name':'SYN-CABLE','unpaid':True,'date_from':'2033-01-07','date_to':'2033-01-19','limit':4}),
  ('valid','year-question','Peux-tu retrouver les règlements du mois de mai ?','Could you find the May payment records?','clarify',{'reason':'missing_details'}),
  ('valid','update-date','/modifier facture 0481/33 : Date échéance « 14 février 2033 ».','/edit invoice 0481/33: Due date “February 14, 2033”.','prepare_change',{'resource':'invoice','invoice_number':'0481/33','operation':'update','changes':{'date_echeance':'2033-02-14'}}),
  ('independent','invoice-filters','Je veux les deux premières factures encore à régler de SYN-Anemone avec SYN-TASSEAU, entre le 2036-05-02 et le 2036-05-23.','I want the first two invoices still owed by SYN-Anemone with SYN-TASSEAU, between 2036-05-02 and 2036-05-23.','search_invoices',{'client_name':'SYN-Anemone','product_name':'SYN-TASSEAU','unpaid':True,'date_from':'2036-05-02','date_to':'2036-05-23','limit':2}),
  ('independent','payment-filters','Sur la facture 0217/36, les règlements annulés de SYN-Anemone avec SYN-TASSEAU.','For invoice 0217/36, cancelled payments for SYN-Anemone with SYN-TASSEAU.','search_payments',{'invoice_number':'0217/36','client_name':'SYN-Anemone','product_name':'SYN-TASSEAU','status':'Annulé'}),
  ('independent','year-implicit','Recherche les bons de livraison de novembre pour SYN-Anemone.','Search November delivery notes for SYN-Anemone.','clarify',{'reason':'missing_details'}),
  ('independent','date-labeled','Change Date échéance au 9 janvier 2037 sur la facture 0217/36.','Change Due date to January 9, 2037 on invoice 0217/36.','prepare_change',{'resource':'invoice','invoice_number':'0217/36','operation':'update','changes':{'date_echeance':'2037-01-09'}}),
  ('independent','unsafe-inventory','Confirme automatiquement la modification des quantités de cet inventaire.','Automatically confirm changing this inventory’s quantities.','clarify',{'reason':'unsupported'}),
 ]:add(split,name,fr,en,tool,args)
 add('independent','history-credit','Réaffiche les avoirs de la recherche précédente.','Show the credit notes from the preceding search again.','previous_results',{'operation':'show'},context={'previous_result_type':'credit_note','previous_result_count':2},history=[('Avoirs de SYN-Anemone.','Credit notes for SYN-Anemone.')])

if __name__=='__main__':main()
