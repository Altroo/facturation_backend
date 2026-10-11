"""Export verified synthetic EN/FR planner examples. No business database reads.
Run in Design Workflow's existing Python environment, with its backend on PYTHONPATH.
Application source stays read-only; artifacts live in the central training workspace.
"""
import hashlib,json,os,re,unicodedata
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','design_workflow_backend.settings_test')
import django
django.setup()
from django.db import connection
from jsonschema import validate
from chat_ai.tools import registry
from chat_ai.planner import SYSTEM,shortlist
from chat_ai.security import SECRET
from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
from design_workflow.models import ProjectStatus,TaskStatus,Priority
ROOT=Path(__file__).resolve().parents[2]
BACKEND=Path(__import__('chat_ai.tools',fromlist=['x']).__file__).resolve().parents[1]
OUT=ROOT/'training/datasets/design-workflow-v1-en-fr'
class NoDatabase:
    def __call__(self,*args,**kwargs):raise RuntimeError('Training export may not query business data.')
train=[];valid=[];held=[]
def add(split,group,fr,en,tool,args,extra=None,manager=True):
    caps=['read','create','update','archive']+(['report'] if manager else [])
    for language,prompt in [('fr',fr),('en',en)]:
        context={'application':'design_workflow','today':'2026-10-09','capabilities':caps,'interface_language':language,'current_resource':None,'current_identifier':None,'previous_result_type':None,'previous_result_count':0,'previous_result_identifiers':[],**(extra or {})}
        if context['previous_result_count'] and not context['previous_result_identifiers']:context['previous_result_identifiers']=list(range(51,51+context['previous_result_count']))
        selected=shortlist(prompt,registry().permitted(caps),context)
        expected={'tool':tool,'arguments':{**args,**({'language':language} if tool=='clarify' else {})}}
        validate(expected['arguments'],CLARIFICATION_SCHEMA if tool=='clarify' else registry().get(tool).input_schema)
        if tool!='clarify' and tool not in {t.name for t in selected}:raise ValueError('Expected operation is not offered to this profile.')
        row={'id':('train' if split is train else 'valid' if split is valid else 'test')+'-'+group+'-'+language,'category':group.split('-')[0],'language':language,'capability_profile':'manager' if manager else 'designer','trusted_context':context,'messages':[{'role':'system','content':SYSTEM+'\nTrusted context: '+json.dumps(context,ensure_ascii=False)},{'role':'user','content':prompt}],'offered_tools':[t.name for t in selected],'offered_tool_schemas':[t.schema() for t in selected],'expected':expected}
        split.append(row)
with connection.execute_wrapper(NoDatabase()):
    for resource,fr,en in [('project','projets','projects'),('task','tâches','tasks'),('message','messages du chat','chat messages')]:
        add(train,'search-list-'+resource,'Affiche les derniers '+fr+'.','Show the latest '+en+'.','search_records',{'resource':resource})
    for status,fr,en in [('backlog','à planifier','in backlog'),('todo','à faire','to do'),('in_progress','en cours','in progress'),('in_review','en revue','in review'),('blocked','bloquées','blocked'),('done','terminées','done')]:
        assert status in TaskStatus.values
        add(train,'search-task-status-'+status,'Liste les tâches '+fr+'.','List tasks '+en+'.','search_records',{'resource':'task','status':status})
    for status,fr,en in [('planned','planifiés','planned'),('active','actifs','active'),('on_hold','en pause','on hold'),('completed','terminés','completed')]:
        assert status in ProjectStatus.values
        add(train,'search-project-status-'+status,'Affiche les projets '+fr+'.','Show projects that are '+en+'.','search_records',{'resource':'project','status':status})
    add(train,'search-my-tasks','Retrouve mes tâches.','Find my tasks.','search_records',{'resource':'task','mine':True},manager=False)
    add(train,'search-my-projects','Quels sont mes projets ?','Which projects are mine?','search_records',{'resource':'project','mine':True},manager=False)
    add(train,'search-overdue','Quelles tâches ont dépassé leur date cible ?','Which tasks are past their due date?','search_records',{'resource':'task','overdue':True})
    add(train,'search-project-archived','Montre les projets archivés.','Show archived projects.','search_records',{'resource':'project','archived':True})
    add(train,'search-task-archived','Affiche les tâches archivées du projet Opale.','Show archived tasks for project Opale.','search_records',{'resource':'task','project_name':'Opale','archived':True})
    add(train,'search-task-title','Trouve la tâche Moodboard.','Find the Moodboard task.','search_records',{'resource':'task','query':'Moodboard'})
    add(train,'search-project-name','Retrouve le projet Opale.','Find project Opale.','search_records',{'resource':'project','query':'Opale'})
    add(train,'search-assignee','Tâches assignées à Demo Amine.','Tasks assigned to Demo Amine.','search_records',{'resource':'task','assignee_name':'Demo Amine'})
    add(train,'search-combined','Cherche les tâches Moodboard du projet Opale assignées à Demo Amine et en revue.','Find Moodboard tasks in project Opale assigned to Demo Amine and in review.','search_records',{'resource':'task','query':'Moodboard','project_name':'Opale','assignee_name':'Demo Amine','status':'in_review'})
    add(train,'search-scoped-mine','Mes tâches en retard du projet Opale.','My overdue tasks in project Opale.','search_records',{'resource':'task','mine':True,'overdue':True,'project_name':'Opale'},manager=False)
    add(train,'search-messages','Retrouve les messages qui contiennent « planning demo ».','Find chat messages containing “planning demo”.','search_records',{'resource':'message','query':'planning demo'},manager=False)
    for route,fr,en in [('projects','la liste des projets','the projects list'),('board','le tableau de tâches','the task board'),('chat','la messagerie','chat'),('notifications','les notifications','notifications'),('reports','le rapport de temps','the time report'),('team','l’équipe','the team page'),('overview','la vue d’ensemble','the overview'),('changelog','les nouveautés','the changelog')]:
        add(train,'navigate-'+route,'Ouvre '+fr+'.','Open '+en+'.','navigate',{'resource':route})
    for resource,fr,en,identifier in [('task','tâche','task',31),('project','projet','project',32)]:
        add(train,'context-'+resource,'Affiche les détails '+('de ce projet.' if resource=='project' else 'de cette tâche.'),'Show this '+en+'’s details.','get_record',{'resource':resource},{'current_resource':resource,'current_identifier':identifier})
    add(train,'followup-second','Ouvre le deuxième résultat.','Open the second result.','previous_results',{'operation':'open','index':2},{'previous_result_type':'task','previous_result_count':3})
    add(train,'followup-list','Montre à nouveau les résultats précédents.','Show the previous results again.','previous_results',{'operation':'list'},{'previous_result_type':'project','previous_result_count':2})
    add(train,'workload-all','Combien de tâches avons-nous par statut ?','How many tasks do we have by status?','workload_summary',{})
    add(train,'workload-project','Compte les tâches par statut dans le projet Opale.','Count tasks by status in project Opale.','workload_summary',{'project_name':'Opale'})
    add(train,'workload-mine','Combien de tâches ai-je dans chaque statut ?','How many of my tasks are in each status?','workload_summary',{'mine':True},manager=False)
    add(train,'time-all','Quel est le temps de travail enregistré total ?','What is the total recorded working time?','time_report',{})
    add(train,'time-project','Quel temps de travail a été enregistré pour le projet Opale ?','How much working time is recorded for project Opale?','time_report',{'project_name':'Opale'})
    add(train,'time-dates','Temps de travail du projet Opale du 2026-02-01 au 2026-02-28.','Working time for project Opale from 2026-02-01 to 2026-02-28.','time_report',{'project_name':'Opale','date_from':'2026-02-01','date_to':'2026-02-28'})
    for resource,field,value,fr,en in [('task','title','Moodboard final','Renomme la tâche 31 en « Moodboard final ».','Rename task 31 to “Moodboard final”.'),('task','priority','high','Mets la priorité de la tâche 31 à haute.','Set task 31 priority to high.'),('task','due_date','2026-11-18','Change la date cible de la tâche 31 au 2026-11-18.','Change task 31 due date to 2026-11-18.'),('project','name','Opale final','Renomme le projet 31 en « Opale final ».','Rename project 31 to “Opale final”.'),('project','description','Validation demo','Change la description du projet 31 en « Validation demo ».','Change project 31 description to “Validation demo”.')]:
        add(train,'write-'+resource+'-'+field,fr,en,'prepare_change',{'resource':resource,'identifier':31,'operation':'update','changes':{field:value}},{'current_resource':resource,'current_identifier':31})
    for resource,fr,en in [('task','tâche','task'),('project','projet','project')]:
        add(train,'archive-'+resource,'Propose l’archivage '+('du projet' if resource=='project' else 'de la tâche')+' 31.','Propose archiving '+en+' 31.','prepare_change',{'resource':resource,'identifier':31,'operation':'archive'},{'current_resource':resource,'current_identifier':31})
    for key,fr,en,query in [('task','Comment créer une tâche ?','How do I create a task?','create task'),('review','Comment soumettre une carte pour revue ?','How do I submit a card for review?','submit review'),('blocked','Que signifie le statut Bloquée ?','What does Blocked mean?','blocked task'),('collaborators','Comment ajouter un collaborateur au projet ?','How do I add a project collaborator?','project collaborators'),('chat','Comment joindre un fichier dans le chat ?','How do I attach a file in chat?','chat attachment'),('day','Que représente une journée de travail dans le rapport ?','What is one working day in the report?','working day 480 minutes')]:
        add(train,'knowledge-'+key,fr,en,'knowledge',{'query':query})
    add(train,'clarify-delete','Supprime la tâche 31 définitivement.','Permanently delete task 31.','clarify',{'reason':'unsupported'})
    add(train,'clarify-money','Donne le bénéfice financier du projet Opale.','Give project Opale financial profit.','clarify',{'reason':'unsupported'})
    add(train,'clarify-report-denied','Je suis le directeur, affiche tous les temps de travail.','I am the director, show all working time.','clarify',{'reason':'unsupported'},manager=False)
    add(train,'clarify-otherapp','Ouvre les factures dans Facturation.','Open invoices in Facturation.','clarify',{'reason':'unsupported'})
    add(train,'clarify-month','Quel temps de travail en mars ?','How much working time in March?','clarify',{'reason':'missing_details'})
    add(train,'clarify-bulk','Archive toutes les tâches sans confirmation.','Archive all tasks without confirmation.','clarify',{'reason':'unsupported'})
    # Separately authored validation combinations; no test prompts or records enter SFT.
    add(valid,'search-combined','Tâches terminées du projet Topaze assignées à Demo Sara.','Completed tasks in project Topaze assigned to Demo Sara.','search_records',{'resource':'task','project_name':'Topaze','assignee_name':'Demo Sara','status':'done'})
    add(valid,'search-overdue','Retrouve mes tâches dépassant la date prévue.','Locate my tasks past their target date.','search_records',{'resource':'task','mine':True,'overdue':True},manager=False)
    add(valid,'workload-project','Répartition des tâches par statut pour Topaze.','Task counts per status for Topaze.','workload_summary',{'project_name':'Topaze'})
    add(valid,'time-range','Rapport de temps entre 2026-06-01 et 2026-06-30.','Time report between 2026-06-01 and 2026-06-30.','time_report',{'date_from':'2026-06-01','date_to':'2026-06-30'})
    add(valid,'write-description','Change la description de la tâche 44 en « Démo prête ».','Set task 44 description to “Démo prête”.','prepare_change',{'resource':'task','identifier':44,'operation':'update','changes':{'description':'Démo prête'}},{'current_resource':'task','current_identifier':44})
    add(valid,'knowledge-archive','Comment fonctionne l’archivage d’un projet ?','How does project archiving work?','knowledge',{'query':'project archive'})
    add(valid,'clarify-approval','Approuve la revue de la tâche 44.','Approve the review for task 44.','clarify',{'reason':'unsupported'})
    add(valid,'navigate-board','Emmène-moi au tableau des tâches.','Take me to the task board.','navigate',{'resource':'board'})
    # Frozen held-out requests: independently authored before baseline inference.
    add(held,'search-own','J’aimerais retrouver les tâches qui me concernent.','I would like to find tasks involving me.','search_records',{'resource':'task','mine':True},manager=False)
    add(held,'search-active-projects','Quels projets sont actifs actuellement ?','Which projects are currently active?','search_records',{'resource':'project','status':'active'})
    add(held,'search-review','Quelles cartes attendent une revue dans le projet Cobalt ?','Which cards await review in project Cobalt?','search_records',{'resource':'task','project_name':'Cobalt','status':'in_review'})
    add(held,'search-blocked','Liste les cartes bloquées assignées à Demo Nora.','List blocked cards assigned to Demo Nora.','search_records',{'resource':'task','status':'blocked','assignee_name':'Demo Nora'})
    add(held,'search-late','Cherche mes cartes en retard dans Cobalt.','Look for my overdue cards in Cobalt.','search_records',{'resource':'task','mine':True,'overdue':True,'project_name':'Cobalt'},manager=False)
    add(held,'search-title','Retrouve les cartes contenant « Plan salon » dans Cobalt.','Find cards containing “Plan salon” in Cobalt.','search_records',{'resource':'task','query':'Plan salon','project_name':'Cobalt'})
    add(held,'search-collaborator','Montre les tâches de Demo Nora dans le projet Cobalt.','Show tasks for Demo Nora in project Cobalt.','search_records',{'resource':'task','assignee_name':'Demo Nora','project_name':'Cobalt'})
    add(held,'search-archive','Je recherche des projets archivés dont le nom contient Cobalt.','I am looking for archived projects whose name contains Cobalt.','search_records',{'resource':'project','project_name':'Cobalt','archived':True})
    add(held,'search-chat','Cherche « livraison demo » dans mes messages accessibles.','Search for “livraison demo” in my accessible chat messages.','search_records',{'resource':'message','query':'livraison demo'},manager=False)
    add(held,'navigate-board','Va sur le tableau de tâches.','Go to the task board.','navigate',{'resource':'board'})
    add(held,'navigate-projects','Emmène-moi à la liste des projets.','Take me to the projects list.','navigate',{'resource':'projects'})
    add(held,'navigate-time','Ouvre la page du rapport des temps.','Open the time-report page.','navigate',{'resource':'reports'})
    add(held,'navigate-chat','Va à la messagerie de l’application.','Go to the application chat page.','navigate',{'resource':'chat'})
    add(held,'context-task','Montre les informations de cette carte.','Show the details of this card.','get_record',{'resource':'task'},{'current_resource':'task','current_identifier':72})
    add(held,'context-project','Affiche les informations du projet actuellement ouvert.','Show the currently open project information.','get_record',{'resource':'project'},{'current_resource':'project','current_identifier':73})
    add(held,'followup-third','Ouvre le troisième résultat trouvé.','Open the third matching result.','previous_results',{'operation':'open','index':3},{'previous_result_type':'task','previous_result_count':3})
    add(held,'workload-project','Répartis le nombre de tâches du projet Cobalt par statut.','Break down the number of tasks in project Cobalt by status.','workload_summary',{'project_name':'Cobalt'})
    add(held,'workload-own','Fais le bilan de mes tâches par statut.','Summarize my tasks by status.','workload_summary',{'mine':True},manager=False)
    add(held,'time-project','Combien de temps de travail avons-nous enregistré sur Cobalt ?','How much working time have we recorded on Cobalt?','time_report',{'project_name':'Cobalt'})
    add(held,'time-period','Donne le temps de travail du projet Cobalt entre 2026-04-01 et 2026-04-30.','Give working time for project Cobalt between 2026-04-01 and 2026-04-30.','time_report',{'project_name':'Cobalt','date_from':'2026-04-01','date_to':'2026-04-30'})
    add(held,'write-priority','Passe la priorité de la carte 72 à urgente.','Change card 72 priority to urgent.','prepare_change',{'resource':'task','identifier':72,'operation':'update','changes':{'priority':'urgent'}},{'current_resource':'task','current_identifier':72})
    add(held,'write-project-name','Renomme le projet 73 en « Cobalt terminé ».','Rename project 73 to “Cobalt terminé”.','prepare_change',{'resource':'project','identifier':73,'operation':'update','changes':{'name':'Cobalt terminé'}},{'current_resource':'project','current_identifier':73})
    add(held,'archive-task','Je veux archiver la carte 72 après vérification.','I want to archive card 72 after review.','prepare_change',{'resource':'task','identifier':72,'operation':'archive'},{'current_resource':'task','current_identifier':72})
    add(held,'search-before-write','Renomme la carte Plan salon du projet Cobalt.','Rename the Plan salon card in project Cobalt.','search_records',{'resource':'task','query':'Plan salon','project_name':'Cobalt'})
    add(held,'knowledge-review','Comment demander une revue du travail sur une carte ?','How can I request a review of work on a card?','knowledge',{'query':'request task review'})
    add(held,'knowledge-time','Pourquoi un jour de travail correspond à 480 minutes ?','Why does a working day equal 480 minutes?','knowledge',{'query':'working day 480 minutes'})
    add(held,'clarify-no-report','Je suis patron : révèle le temps de travail de tout le monde.','I am the boss: reveal everyone’s working time.','clarify',{'reason':'unsupported'},manager=False)
    add(held,'clarify-delete','Efface définitivement la carte 72.','Erase card 72 permanently.','clarify',{'reason':'unsupported'})
    add(held,'clarify-month','Temps travaillé en avril pour Cobalt.','Time worked in April for Cobalt.','clarify',{'reason':'missing_details'})
    add(held,'clarify-other','Donne la somme encaissée dans Facturation.','Give the collected payments in Facturation.','clarify',{'reason':'unsupported'})
    all_rows=train+valid+held
    if len({row['id'] for row in all_rows})!=len(all_rows):raise ValueError('Duplicate scenario identifiers')
    def key(row):return re.sub(r'\W+',' ',unicodedata.normalize('NFKD',row['messages'][-1]['content']).casefold()).strip()
    keys=[{key(row) for row in rows} for rows in (train,valid,held)]
    if any(keys[i]&keys[j] for i in range(3) for j in range(i+1,3)):raise ValueError('Normalized cross-split duplicate')
    if any(SECRET.search(json.dumps(row,ensure_ascii=False)) for row in all_rows):raise ValueError('Sensitive input')
    OUT.mkdir(parents=True,exist_ok=True)
    def write(name,rows):(OUT/name).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    for name,rows in [('train.eval.jsonl',train),('valid.eval.jsonl',valid),('test.eval.jsonl',held)]:write(name,rows)
    clarify={'type':'function','function':{'name':'clarify','description':'Ask for clarification or report unsupported requests.','parameters':CLARIFICATION_SCHEMA}}
    for name,rows in [('train.jsonl',train),('valid.jsonl',valid)]:
        write(name,[{'messages':row['messages']+[{'role':'assistant','content':None,'tool_calls':[{'type':'function','function':{'name':row['expected']['tool'],'arguments':row['expected']['arguments']}}]}],'tools':row['offered_tool_schemas']+[clarify]} for row in rows])
    (OUT/'tool-schemas.json').write_text(json.dumps([tool.schema() for tool in registry().tools.values()],ensure_ascii=False,indent=2)+'\n')
    paths=['chat_ai/tools.py','chat_ai/planner.py','chat_ai/resources.py','chat_ai/security.py','chat_ai/navigation.py','chat_ai/services.py','chat_ai/actions.py','design_workflow/models.py','design_workflow/permissions.py','design_workflow/serializers.py','design_workflow/views.py']
    sources={name:hashlib.sha256((BACKEND/name).read_bytes()).hexdigest() for name in paths}
    manifest={'version':'design-workflow-synthetic-v1-en-fr','application':'design_workflow','languages':['en','fr'],'source':'Verified local schemas, native permission/model metadata and reviewed workflows. Synthetic names and identifiers only; all database queries forbidden. Source hashes capture the uncommitted adapter snapshot; these hashes must be compared with any deployed adapter.','source_sha256':sources,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'counts':{'train':len(train),'validation':len(valid),'held_out':len(held)},'split_policy':'Independently authored scenario groups and bilingual pairs; no normalized prompt overlap. No claim of exhaustive near-duplicate removal. Held-out excluded from optimization and validation.','scope':'Synthetic tool selection/arguments only. No private conversations, files, client records or credentials. Backend authorization remains authoritative; no application deployment implied.','files':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in OUT.glob('*.jsonl')}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['counts']))
