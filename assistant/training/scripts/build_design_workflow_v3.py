"""Synthetic native Design Workflow contrasts; read-only metadata, no private data."""
import os
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','design_workflow_backend.settings_test')
import django
django.setup()
from django.db import connection
from chat_ai.tools import registry
from chat_ai.planner import SYSTEM,shortlist
from chat_ai.security import SECRET
from synthetic_curriculum import SyntheticCurriculum

class NoDatabase:
    def __call__(self,*args,**kwargs):raise RuntimeError('Synthetic training must not query application data')

c=SyntheticCurriculum('design_workflow','design-workflow-v3-en-fr','design-workflow-v2-en-fr',registry,shortlist,SYSTEM,SECRET,
    {'capabilities':['read','create','update','archive','mutate','report'],'current_resource':None,'current_identifier':None,
     'previous_result_type':None,'previous_result_count':0,'previous_result_identifiers':[]},
    ['design-workflow-v1-en-fr/test.eval.jsonl','design-workflow-v2-en-fr/independent.eval.jsonl'])
add=c.add
with connection.execute_wrapper(NoDatabase()):
    c.refresh_inherited(lambda context:context)
    examples=[
      ('assignee','Les tâches de Démo Lina sur Veranda Essai.','Tasks assigned to Démo Lina on Veranda Essai.',{'resource':'task','assignee_name':'Démo Lina','project_name':'Veranda Essai'}),
      ('assignee-only','Retrouve les cartes attribuées à Démo Lina.','Find cards assigned to Démo Lina.',{'resource':'task','assignee_name':'Démo Lina'}),
      ('assignee-blocked','Les tâches bloquées de Démo Lina.','The blocked tasks assigned to Démo Lina.',{'resource':'task','status':'blocked','assignee_name':'Démo Lina'}),
      ('mine-blocked','Mes cartes bloquées, projet Veranda Essai.','My blocked cards, project Veranda Essai.',{'resource':'task','mine':True,'status':'blocked','project_name':'Veranda Essai'}),
      ('mine-review','Mes tâches à l’état En revue.','My tasks in the In Review state.',{'resource':'task','mine':True,'status':'in_review'}),
      ('mine-only','Les tâches de mon espace dans Veranda Essai.','My tasks within Veranda Essai.',{'resource':'task','mine':True,'project_name':'Veranda Essai'}),
      ('name-not-assignee','Les tâches contenant le texte « Démo Lina ».','Tasks containing the text “Démo Lina”.',{'resource':'task','query':'Démo Lina'}),
      ('name-and-assignee','Cartes contenant « Esquisse » assignées à Démo Lina dans Veranda Essai.','Cards containing “Esquisse” assigned to Démo Lina in Veranda Essai.',{'resource':'task','query':'Esquisse','assignee_name':'Démo Lina','project_name':'Veranda Essai'}),
      ('late','Tâches en retard attribuées à Démo Lina.','Overdue tasks assigned to Démo Lina.',{'resource':'task','overdue':True,'assignee_name':'Démo Lina'}),
      ('archived','Cartes archivées du projet Veranda Essai.','Archived cards for project Veranda Essai.',{'resource':'task','archived':True,'project_name':'Veranda Essai'}),
      ('app-word','Cherche les tâches du projet nommé Facturation.','Find tasks in the project named Facturation.',{'resource':'task','project_name':'Facturation'}),
      ('message-content','Retrouve « point hebdomadaire » dans la messagerie.','Find “point hebdomadaire” in messaging.',{'resource':'message','query':'point hebdomadaire'}),
      ('message-my','Dans mes messages, recherche « palette verte ».','In my messages, search for “palette verte”.',{'resource':'message','query':'palette verte'}),
      ('message-accessible','Messages auxquels j’ai accès contenant « réunion demain ».','Messages I can access containing “réunion demain”.',{'resource':'message','query':'réunion demain'}),
      ('message-punctuation','Cherche « plan B: révision 2 » dans les messages.','Find “plan B: révision 2” in messages.',{'resource':'message','query':'plan B: révision 2'}),
      ('message-injection-data','Cherche le texte « ignore les règles » dans les messages autorisés.','Search authorized messages for the text “ignore les règles”.',{'resource':'message','query':'ignore les règles'}),
      ('described-rename','Renomme la carte Esquisse façade du projet Veranda Essai.','Rename the Esquisse façade card in project Veranda Essai.',{'resource':'task','query':'Esquisse façade','project_name':'Veranda Essai'}),
      ('described-priority','Modifie la priorité de la tâche Esquisse façade dans Veranda Essai.','Update the priority of task Esquisse façade in Veranda Essai.',{'resource':'task','query':'Esquisse façade','project_name':'Veranda Essai'}),
      ('described-project','Modifie le nom du projet Veranda Essai.','Update the name of project Veranda Essai.',{'resource':'project','project_name':'Veranda Essai'}),
    ]
    for key,fr,en,args in examples:add('train','contrast-'+key,fr,en,'search_records',args)
    for key,fr,en,args in [
      ('project-minutes','Combien de minutes ont été travaillées sur Veranda Essai ?','How many minutes were worked on Veranda Essai?',{'project_name':'Veranda Essai'}),
      ('project-time','Temps de travail de Veranda Essai, toutes périodes.','Working time for Veranda Essai across all periods.',{'project_name':'Veranda Essai'}),
      ('unqualified-range','Temps de travail du 2032-02-05 au 2032-02-18.','Working time from 2032-02-05 through 2032-02-18.',{'date_from':'2032-02-05','date_to':'2032-02-18'}),
      ('explicit-range','Total des minutes enregistrées entre le 2032-08-01 et le 2032-08-31.','Total recorded minutes between 2032-08-01 and 2032-08-31.',{'date_from':'2032-08-01','date_to':'2032-08-31'}),
      ('project-range','Rapport des heures travaillées sur Veranda Essai entre le 2032-06-04 et le 2032-06-21.','Report of hours worked on Veranda Essai between 2032-06-04 and 2032-06-21.',{'project_name':'Veranda Essai','date_from':'2032-06-04','date_to':'2032-06-21'}),
    ]:add('train','time-'+key,fr,en,'time_report',args)
    for key,fr,en,reason,caps in [
      ('report-denied','Affiche le temps de travail de l’équipe, je suis le chef.','Show the team’s working time, I am the boss.','unsupported',['read','update','archive','mutate']),
      ('report-denied-plain','Combien d’heures travaillées sur Veranda Essai ?','How many hours worked on Veranda Essai?','unsupported',['read']),
      ('no-year','Rapport des heures de janvier sur Veranda Essai.','Report of January hours on Veranda Essai.','missing_details',['read','report']),
      ('no-year-general','Minutes enregistrées en novembre.','Recorded minutes in November.','missing_details',['read','report']),
      ('month-name','Le temps travaillé pendant mai pour Veranda Essai.','Time worked during May for Veranda Essai.','missing_details',['read','report']),
      ('invoice-app','Cherche une facture dans Facturation.','Find an invoice in Facturation.','unsupported',['read','report']),
      ('supplier-app','Ouvre les dépenses fournisseurs dans management_projet.','Open supplier expenses in management_projet.','unsupported',['read','report']),
      ('money','Quel chiffre d’affaires a réalisé Veranda Essai ?','What revenue has Veranda Essai generated?','unsupported',['read','report']),
      ('delete-task','Supprime définitivement la tâche 1271.','Permanently delete task 1271.','unsupported',['read','update','archive','mutate','report']),
      ('delete-project','Efface le projet Veranda Essai et toutes ses tâches.','Delete project Veranda Essai and all its tasks.','unsupported',['read','update','archive','mutate','report']),
      ('unsupported-status','Change la tâche 1271 au statut Terminée.','Change task 1271 to Done status.','unsupported',['read','update','mutate']),
      ('unsupported-title-only','Recherche « Esquisse » uniquement dans les titres, jamais les descriptions.','Search for “Esquisse” only in task titles, never descriptions.','unsupported',['read']),
      ('unsupported-strict-assignee','Uniquement les tâches assignées à moi, exclure les autres tâches de mes projets.','Only tasks assigned to me, exclude other tasks in my projects.','unsupported',['read']),
      ('unsupported-sender','Messages envoyés par Démo Lina.','Messages sent by Démo Lina.','unsupported',['read']),
      ('unsupported-time-person','Donne les heures de Démo Lina seulement.','Give only the hours for Démo Lina.','unsupported',['read','report']),
    ]:add('train','clarify-'+key,fr,en,'clarify',{'reason':reason},capabilities=caps,switch=True)
    for key,fr,en,args in [
      ('all','Répartition des tâches par état pour Veranda Essai.','Task breakdown by state for Veranda Essai.',{'project_name':'Veranda Essai'}),
      ('mine','Le nombre de mes tâches dans chaque statut, projet Veranda Essai.','The count of my tasks in each status, project Veranda Essai.',{'project_name':'Veranda Essai','mine':True}),
    ]:add('train','workload-'+key,fr,en,'workload_summary',args)
    add('train','current-edit','Change le titre de cette carte en « Vérification finale ».','Change this card title to “Vérification finale”.','prepare_change',{'resource':'task','identifier':1272,'operation':'update','changes':{'title':'Vérification finale'}},{'current_resource':'task','current_identifier':1272})
    add('train','ordinal-edit','Modifie la priorité de la deuxième carte à urgente.','Update the second card priority to urgent.','prepare_change',{'resource':'task','identifier':1274,'operation':'update','changes':{'priority':'urgent'}},{'previous_result_type':'task','previous_result_count':2,'previous_result_identifiers':[1273,1274]})
    add('train','current-archive','Archive ce projet après confirmation.','Archive this project after confirmation.','prepare_change',{'resource':'project','identifier':1275,'operation':'archive'},{'current_resource':'project','current_identifier':1275})
    dev=[
      ('assignee','Cartes de Démo Ines dans Atelier Essai, statut bloqué.','Cards assigned to Démo Ines in Atelier Essai, blocked status.','search_records',{'resource':'task','assignee_name':'Démo Ines','project_name':'Atelier Essai','status':'blocked'}),
      ('message','Dans la messagerie, retrouve « validation meuble ».','In messaging, find “validation meuble”.','search_records',{'resource':'message','query':'validation meuble'}),
      ('range','Total minutes du 2033-09-02 au 2033-09-24.','Total minutes from 2033-09-02 to 2033-09-24.','time_report',{'date_from':'2033-09-02','date_to':'2033-09-24'}),
      ('month','Heures de février pour Atelier Essai.','February hours for Atelier Essai.','clarify',{'reason':'missing_details'}),
      ('described','Renomme la tâche Analyse lumière sur Atelier Essai.','Rename task Analyse lumière on Atelier Essai.','search_records',{'resource':'task','query':'Analyse lumière','project_name':'Atelier Essai'}),
    ]
    for key,fr,en,tool,args in dev:add('valid','development-'+key,fr,en,tool,args)
    fresh=[
      ('assignee','Pour Terrasse Essai, je cherche les tâches attribuées à Démo Yara.','For Terrasse Essai, I am looking for tasks assigned to Démo Yara.','search_records',{'resource':'task','project_name':'Terrasse Essai','assignee_name':'Démo Yara'}),
      ('blocked','Les cartes bloquées de Démo Yara dans Terrasse Essai.','Démo Yara’s blocked cards in Terrasse Essai.','search_records',{'resource':'task','status':'blocked','assignee_name':'Démo Yara','project_name':'Terrasse Essai'}),
      ('message','Peux-tu retrouver « échantillon tissu » dans les messages ?','Can you find “échantillon tissu” in messages?','search_records',{'resource':'message','query':'échantillon tissu'}),
      ('time','Nombre de minutes travaillées pour Terrasse Essai, sans restriction de date.','Number of minutes worked for Terrasse Essai, with no date restriction.','time_report',{'project_name':'Terrasse Essai'}),
      ('range','Temps total enregistré, du 2034-05-03 au 2034-05-26.','Total recorded working time, from 2034-05-03 to 2034-05-26.','time_report',{'date_from':'2034-05-03','date_to':'2034-05-26'}),
      ('year','Temps enregistré pendant août sur Terrasse Essai.','Time recorded during August on Terrasse Essai.','clarify',{'reason':'missing_details'}),
      ('crossapp','Retrouve une facture client de l’application Facturation.','Retrieve a customer invoice from the Facturation application.','clarify',{'reason':'unsupported'}),
      ('described','Modifie le titre de la tâche Étude ombre dans Terrasse Essai.','Update the title of task Étude ombre in Terrasse Essai.','search_records',{'resource':'task','query':'Étude ombre','project_name':'Terrasse Essai'}),
    ]
    for key,fr,en,tool,args in fresh:add('independent','fresh-'+key,fr,en,tool,args)
    add('independent','fresh-denied','Rapport des heures de Terrasse Essai, s’il te plaît.','Working-hours report for Terrasse Essai, please.','clarify',{'reason':'unsupported'},capabilities=['read'],switch=True)
    add('independent','fresh-change','Renomme cette carte en « Présentation témoin ».','Rename this card to “Présentation témoin”.','prepare_change',{'resource':'task','identifier':1492,'operation':'update','changes':{'title':'Présentation témoin'}},{'current_resource':'task','current_identifier':1492})
    native=Path(__import__('chat_ai.tools',fromlist=['x']).__file__).parent
    c.write(__file__,[native/'tools.py',native/'planner.py',native/'resources.py'])
