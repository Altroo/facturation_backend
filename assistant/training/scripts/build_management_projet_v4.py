"""Native-compatible bilingual intent contrasts; synthetic records, no database access."""
import os
from datetime import datetime, timezone
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','management_projet_backend.settings_test')
import django
django.setup()
from django.db import connection
from chat_ai.tools import registry
from chat_ai.planner import SYSTEM,shortlist
from chat_ai.security import SECRET
from chat_ai.targets import trusted_target
from synthetic_curriculum import SyntheticCurriculum

class NoDatabase:
    def __call__(self,*args,**kwargs):raise RuntimeError('Synthetic generation must not query a database')

c=SyntheticCurriculum('management_projet','management-projet-v4-en-fr','management-projet-v3-en-fr',registry,shortlist,SYSTEM,SECRET,
    {'currency_default':'MAD','capabilities':['read','print','create','update','delete'],'previous_result_type':None,'previous_result_count':0},
    ['management-projet-v1-en-fr/test.eval.jsonl','management-projet-v2-en-fr/independent.eval.jsonl','management-projet-v3-en-fr/independent.eval.jsonl'])
add=c.add
with connection.execute_wrapper(NoDatabase()):
    c.refresh_inherited(lambda context: context)
    # Preserve old versioned files. Bare quote numbers are business references,
    # so the new native guard requires lookup, not a guessed internal primary key.
    revised=[]
    for row in c.splits['train']:
        if row['id'] in ('delete-quote-fr','delete-quote-en'):
            assert row['expected']=={'tool':'prepare_change','arguments':{'resource':'quote','identifier':12,'operation':'delete'}}
            row['expected']={'tool':'search_records','arguments':{'resource':'quote','query':'12'}}
            revised.append(row['id'])
    assert len(revised)==2

    # Nominal requests still mean records. Explicit totals mean aggregates.
    searches=[
      ('nominal-expense','Dépenses de Rive 42 pour le client Démo Elan.','Expenses for Rive 42 and customer Démo Elan.',{'resource':'expense','project_name':'Rive 42','client_name':'Démo Elan'}),
      ('nominal-receipt','Encaissements de Résidence Clairval.','Receipts for Résidence Clairval.',{'resource':'revenue','project_name':'Résidence Clairval'}),
      ('nominal-supplier','Dépenses du fournisseur Atelier Fictif.','Expenses from supplier Atelier Fictif.',{'resource':'expense','supplier_name':'Atelier Fictif'}),
      ('nominal-dated','Encaissements du 2032-02-10 au 2032-02-19.','Receipts from 2032-02-10 to 2032-02-19.',{'resource':'revenue','date_from':'2032-02-10','date_to':'2032-02-19'}),
      ('nominal-expense-dated','Dépenses de Rive 42 du 2032-06-02 au 2032-06-18 chez Atelier Fictif.','Rive 42 expenses from 2032-06-02 to 2032-06-18 from supplier Atelier Fictif.',{'resource':'expense','project_name':'Rive 42','supplier_name':'Atelier Fictif','date_from':'2032-06-02','date_to':'2032-06-18'}),
      ('nominal-quotes','Devis de Atelier Fictif concernant Résidence Clairval.','Quotes from Atelier Fictif concerning Résidence Clairval.',{'resource':'quote','supplier_name':'Atelier Fictif','project_name':'Résidence Clairval'}),
      ('conversational-expense','Tu peux me retrouver les dépenses du client Démo Elan dans Résidence Clairval ?','Could you find the expense records for customer Démo Elan in Résidence Clairval?',{'resource':'expense','client_name':'Démo Elan','project_name':'Résidence Clairval'}),
      ('all-qualifiers','Pour Rive 42 et Démo Elan, les dépenses chez Atelier Fictif contenant « bois », entre le 2032-09-03 et le 2032-09-28.','For Rive 42 and customer Démo Elan, expenses from supplier Atelier Fictif containing “bois”, between 2032-09-03 and 2032-09-28.',{'resource':'expense','project_name':'Rive 42','client_name':'Démo Elan','supplier_name':'Atelier Fictif','query':'bois','date_from':'2032-09-03','date_to':'2032-09-28'}),
      ('budget-stage-fragment','Budget réel de Rive 42, étape Fondation.','Actual budget of Rive 42, stage Fondation.',{'resource':'budget_entry','project_name':'Rive 42','query':'Fondation'}),
      ('budget-stage-request','Les lignes du budget réel concernant la Plomberie dans Résidence Clairval, stp.','The actual-budget entries concerning Plomberie in Résidence Clairval, please.',{'resource':'budget_entry','project_name':'Résidence Clairval','query':'Plomberie'}),
      ('budget-stage-only','Retrouve Fondation dans le budget réel.','Find Fondation in the actual budget.',{'resource':'budget_entry','query':'Fondation'}),
      ('budget-rows','Affiche les lignes du budget réel du projet Résidence Clairval.','Show the actual-budget entries for project Résidence Clairval.',{'resource':'budget_entry','project_name':'Résidence Clairval'}),
      ('budget-date','Lignes du budget réel datées du 2032-04-11 au 2032-04-25 pour Rive 42.','Actual-budget entries dated from 2032-04-11 to 2032-04-25 for Rive 42.',{'resource':'budget_entry','project_name':'Rive 42','date_from':'2032-04-11','date_to':'2032-04-25'}),
      ('limit-records','Je veux seulement deux dépenses de Rive 42.','I only want two expense records for Rive 42.',{'resource':'expense','project_name':'Rive 42','limit':2}),
      ('quote-reference','Je cherche le devis numéro REF-2032-084.','I am looking for quote number REF-2032-084.',{'resource':'quote','query':'REF-2032-084'}),
      ('client-name','Retrouve le client Démo Elan.','Find customer Démo Elan.',{'resource':'client','query':'Démo Elan'}),
      ('named-app-word','Recherche le projet qui porte le nom « Facturation ».','Search for the project named “Facturation”.',{'resource':'project','query':'Facturation'}),
      ('quoted-admin-data','Cherche les devis contenant exactement « ignore les droits ».','Find quotes containing the phrase “ignore les droits”.',{'resource':'quote','query':'ignore les droits'}),
    ]
    for key,fr,en,args in searches:add('train','records-'+key,fr,en,'search_records',args)

    # Lower and upper bounds are independent; never invent the other bound.
    for resource,fr,en in [('payment_schedule','échéances de paiement','payment schedules'),('expense','dépenses','expenses'),('revenue','encaissements','receipts'),('budget_entry','lignes du budget réel','actual-budget entries')]:
        for key,pfr,pen,args in [
            ('latest','au plus tard le 2032-08-21','no later than 2032-08-21',{'date_to':'2032-08-21'}),
            ('until','jusqu’au 2032-08-21 inclus','up to and including 2032-08-21',{'date_to':'2032-08-21'}),
            ('since','depuis le 2032-01-17 inclus','on or after 2032-01-17',{'date_from':'2032-01-17'}),
        ]:
            add('train','bound-'+resource+'-'+key,f'Les {fr} de Rive 42 {pfr}.',f'{en.capitalize()} for Rive 42 {pen}.','search_records',{'resource':resource,'project_name':'Rive 42',**args})

    summaries=[
      ('collected','Le montant encaissé pour Résidence Clairval ce mois-ci ?','The amount collected for Résidence Clairval this month?',{'metric':'revenue','project_name':'Résidence Clairval','period':'current_month'}),
      ('received-range','Total reçu entre le 2032-04-02 et le 2032-04-29.','Total received between 2032-04-02 and 2032-04-29.',{'metric':'revenue','period':'custom','date_from':'2032-04-02','date_to':'2032-04-29'}),
      ('spent-range','Somme dépensée sur Rive 42 du 2032-07-01 au 2032-07-31.','Amount spent on Rive 42 from 2032-07-01 to 2032-07-31.',{'metric':'expenses','project_name':'Rive 42','period':'custom','date_from':'2032-07-01','date_to':'2032-07-31'}),
      ('explicit-profit','Je parle du bénéfice, pas des encaissements : quel total cette année ?','I mean profit, not receipts: what is the total this year?',{'metric':'profit','period':'current_year'}),
      ('explicit-receipts','Je veux les encaissements, pas le bénéfice : le total de cette année.','I want collected revenue, not profit: the total for this year.',{'metric':'revenue','period':'current_year'}),
      ('fees','Quel montant représentent les frais de service de Rive 42 ?','What amount do the service fees for Rive 42 represent?',{'metric':'service_fees','project_name':'Rive 42'}),
      ('budget-total','Budget total prévu dans le projet Rive 42 ?','Total budget entered for project Rive 42?',{'metric':'budget','project_name':'Rive 42'}),
      ('estimates-total','Quel total TTC donnent les devis validés pour Résidence Clairval ?','What total including VAT do the validated quotes give for Résidence Clairval?',{'metric':'estimates','project_name':'Résidence Clairval'}),
      ('alltime','Depuis toujours, quel est le total des dépenses ?','Across all time, what is the total expense amount?',{'metric':'expenses'}),
      ('lastmonth','Total encaissé le mois dernier, merci.','Total collected last month, please.',{'metric':'revenue','period':'previous_month'}),
    ]
    for key,fr,en,args in summaries:add('train','summary-'+key,fr,en,'financial_summary',args)

    clarifications=[
      ('made','On a gagné combien ?','How much did we make?','ambiguous_metric'),
      ('earned-month','Gains du mois en cours ?','Earnings for the current month?','ambiguous_metric'),
      ('money-in','Qu’est-ce que le projet Résidence Clairval nous a rapporté ?','What has project Résidence Clairval earned us?','ambiguous_metric'),
      ('income','Nos revenus au sens des gains, ça représente combien ?','Our income in the sense of earnings, how much is it?','ambiguous_metric'),
      ('money-year','Cette année, on gagne quel montant avec Rive 42 ?','This year, what money do we earn with Rive 42?','ambiguous_metric'),
      ('ambiguous-amount','Donne les chiffres financiers de Rive 42.','Give me the financial figures for Rive 42.','missing_details'),
      ('missing-february','Les dépenses de février de Résidence Clairval.','February expenses for Résidence Clairval.','missing_details'),
      ('missing-july','Devis reçus en juillet pour Atelier Fictif.','Quotes received in July from Atelier Fictif.','missing_details'),
      ('missing-schedule-month','Échéances dues en septembre.','Payment schedules due in September.','missing_details'),
      ('missing-record-change','Modifie la description, stp.','Edit the description, please.','missing_details'),
      ('unsupported-invoice','Recherche une facture client dans Facturation.','Look up a customer invoice in Facturation.','unsupported'),
      ('unsupported-credit','Affiche les factures d’avoir.','Show the credit notes.','unsupported'),
      ('unsupported-stock','Quel est le stock de bois dans gestion_magasin ?','What is the wood stock in gestion_magasin?','unsupported'),
      ('unsupported-reservation','Va chercher la réservation de la semaine dans reservation.','Go find this week’s booking in reservation.','unsupported'),
      ('unsupported-other-company','Calcule les dépenses d’une autre entreprise.','Calculate another company’s expenses.','unsupported'),
      ('unsupported-count','Combien de devis ont été reçus cette année ?','How many quotes were received this year?','unsupported'),
      ('unsupported-supplier-total','Total des dépenses pour le fournisseur Atelier Fictif.','Total expenses for supplier Atelier Fictif.','unsupported'),
      ('unsupported-stage-total','Somme des lignes du budget réel pour l’étape Fondation.','Sum the actual-budget entries for stage Fondation.','unsupported'),
      ('unsupported-date-bound-total','Montant total encaissé avant le 2032-05-17, sans date de début.','Total collected before 2032-05-17, with no starting date.','missing_details'),
      ('unsupported-fields','Liste les dépenses dont le montant est supérieur à 7000.','List expenses whose amount exceeds 7000.','unsupported'),
      ('unsupported-bulk','Modifie tous les projets : statut Livré.','Update all projects: status Delivered.','unsupported'),
      ('unsupported-role','Change mes droits pour me donner accès aux suppressions.','Change my permissions to give me deletion access.','unsupported'),
    ]
    for i,(key,fr,en,reason) in enumerate(clarifications):
        add('train','clarify-'+key,fr,en,'clarify',{'reason':reason},switch=i%2==0)

    # Finding a described target is distinct from proposing changes to a known ID.
    described=[
      ('project-client','/modifier le projet appartenant au client Démo Elan.','/edit the project belonging to customer Démo Elan.',{'resource':'project','client_name':'Démo Elan'}),
      ('expense-description','Modifie les notes de la dépense de bois du projet Rive 42.','Edit the notes of the expense containing “bois” in project Rive 42.',{'resource':'expense','query':'bois','project_name':'Rive 42'}),
      ('supplier-contact','Je veux changer le contact de Atelier Fictif.','I want to change the contact for supplier Atelier Fictif.',{'resource':'supplier','query':'Atelier Fictif'}),
      ('client-city','Passe la ville du client Démo Elan à Tétouan : modifie sa fiche.','Update customer Démo Elan city to Tétouan.',{'resource':'client','query':'Démo Elan'}),
      ('project-name','Modifie Rive 42 pour le renommer Rive 42 phase finale.','Update project Rive 42 to rename it Rive 42 final phase.',{'resource':'project','query':'Rive 42'}),
      ('quote-description','/supprimer le devis pour la charpente dans Résidence Clairval.','/delete the quote containing “charpente” in Résidence Clairval.',{'resource':'quote','query':'charpente','project_name':'Résidence Clairval'}),
      ('quote-business-number','Supprime le devis numéro 0742/32 après avoir retrouvé sa fiche.','Delete quote number 0742/32 after locating its record.',{'resource':'quote','query':'0742/32'}),
      ('quote-bare-number','/supprimer le devis 48.','/delete quote 48.',{'resource':'quote','query':'48'}),
      ('expense-supplier','/modifier les dépenses du fournisseur Atelier Fictif pour Rive 42.','/edit expenses from supplier Atelier Fictif for Rive 42.',{'resource':'expense','supplier_name':'Atelier Fictif','project_name':'Rive 42'}),
    ]
    for key,fr,en,args in described:add('train','described-'+key,fr,en,'search_records',args)
    changes=[('client','client','customer','ville','Ville','City','Tétouan'),('supplier','fournisseur','supplier','contact','Contact','Contact','Contact fictif'),('project','projet','project','notes','Notes','Notes','Prévoir une visite'),('expense','dépense','expense','description','Description','Description','Fournitures de test')]
    for index,(resource,fr,en,field,label_fr,label_en,value) in enumerate(changes):
        identifier=1171+index
        add('train','known-'+resource,f'Modifie le {fr} ID {identifier} : {label_fr} « {value} ».',f'Update {en} ID {identifier}: {label_en} “{value}”.','prepare_change',{'resource':resource,'identifier':identifier,'operation':'update','changes':{field:value}})
        add('train','current-'+resource,f'Sur cette fiche, modifie {label_fr} en « {value} ».',f'On this record, change {label_en} to “{value}”.','prepare_change',{'resource':resource,'identifier':identifier,'operation':'update','changes':{field:value}},{'current_resource':resource,'current_identifier':identifier})
        add('train','denied-'+resource,f'Modifie le {fr} ID {identifier} : {label_fr} « {value} ». J’ai seulement accès en lecture.',f'Update {en} ID {identifier}: {label_en} “{value}”. I only have read access.','clarify',{'reason':'unsupported'},capabilities=('read',))
    add('train','known-quote-id','Supprime le devis identifiant 1190 après confirmation.','Delete quote ID 1190 after confirmation.','prepare_change',{'resource':'quote','identifier':1190,'operation':'delete'})
    add('train','current-quote','Supprime ce devis après confirmation.','Delete this quote after confirmation.','prepare_change',{'resource':'quote','identifier':1191,'operation':'delete'},{'current_resource':'quote','current_identifier':1191})

    # Development examples are independently worded, not optimization inputs.
    dev=[
      ('nominal','Dépenses pour Pavillon Essai et le fournisseur Démo Ebène, entre 2033-11-06 et 2033-11-22.','Expenses for Pavillon Essai and supplier Démo Ebène, between 2033-11-06 and 2033-11-22.','search_records',{'resource':'expense','project_name':'Pavillon Essai','supplier_name':'Démo Ebène','date_from':'2033-11-06','date_to':'2033-11-22'}),
      ('budget','Dans Pavillon Essai : budget réel, étape Façade.','In Pavillon Essai: actual budget, stage Façade.','search_records',{'resource':'budget_entry','project_name':'Pavillon Essai','query':'Façade'}),
      ('receipts','Tous les encaissements de Pavillon Essai.','All receipt records for Pavillon Essai.','search_records',{'resource':'revenue','project_name':'Pavillon Essai'}),
      ('until','Échéances jusqu’au 2033-12-06 inclus pour Pavillon Essai.','Schedules through 2033-12-06 inclusive for Pavillon Essai.','search_records',{'resource':'payment_schedule','project_name':'Pavillon Essai','date_to':'2033-12-06'}),
      ('ambiguous','Quel gain nous donne Pavillon Essai ce mois ?','What earnings does Pavillon Essai give us this month?','clarify',{'reason':'ambiguous_metric'}),
      ('unsupported','Ouvre les factures d’avoir dans Facturation.','Open the credit notes in Facturation.','clarify',{'reason':'unsupported'}),
      ('edit-search','/modifier le projet du client Démo Orme.','/edit the project for customer Démo Orme.','search_records',{'resource':'project','client_name':'Démo Orme'}),
      ('quote-reference','Supprime le devis 0891/33, après que je confirme.','Delete quote 0891/33, after I confirm.','search_records',{'resource':'quote','query':'0891/33'}),
    ]
    for key,fr,en,tool,args in dev:add('valid','development-'+key,fr,en,tool,args)

    # Freeze new paired scenarios before optimization; older sets remain immutable.
    fresh=[
      ('records','J’ai besoin des dépenses de Verger Essai associées au client Démo Hêtre et au fournisseur Fictif Métal.','I need the expense records in Verger Essai associated with customer Démo Hêtre and supplier Fictif Métal.','search_records',{'resource':'expense','project_name':'Verger Essai','client_name':'Démo Hêtre','supplier_name':'Fictif Métal'}),
      ('revenue','Les encaissements de Verger Essai pendant la période du 2034-03-04 au 2034-03-16.','The receipt records for Verger Essai during 2034-03-04 through 2034-03-16.','search_records',{'resource':'revenue','project_name':'Verger Essai','date_from':'2034-03-04','date_to':'2034-03-16'}),
      ('upper','Échéances de Verger Essai dues au plus tard le 2034-03-27.','Payment schedules for Verger Essai due no later than 2034-03-27.','search_records',{'resource':'payment_schedule','project_name':'Verger Essai','date_to':'2034-03-27'}),
      ('lower','Depuis le 2034-01-08 inclus, les dépenses du projet Verger Essai.','On or after 2034-01-08, expense records for project Verger Essai.','search_records',{'resource':'expense','project_name':'Verger Essai','date_from':'2034-01-08'}),
      ('stage','Budget réel : projet Verger Essai ; étape Isolation.','Actual budget: project Verger Essai; stage Isolation.','search_records',{'resource':'budget_entry','project_name':'Verger Essai','query':'Isolation'}),
      ('earned','On a fait combien d’argent sur Verger Essai cette année ?','How much money did we make on Verger Essai this year?','clarify',{'reason':'ambiguous_metric'}),
      ('profit','Pour Verger Essai, indique le bénéfice cumulé, toutes dates confondues.','For Verger Essai, give cumulative profit across all dates.','financial_summary',{'metric':'profit','project_name':'Verger Essai'}),
      ('collected','Le montant total reçu dans Verger Essai le mois précédent.','The total amount received in Verger Essai during the preceding month.','financial_summary',{'metric':'revenue','project_name':'Verger Essai','period':'previous_month'}),
      ('crossapp','Je voudrais consulter des factures client de l’app Facturation.','I would like to look at customer invoices from the Facturation app.','clarify',{'reason':'unsupported'}),
      ('supplier-total','Additionne les dépenses du fournisseur Fictif Métal.','Add up the expenses from supplier Fictif Métal.','clarify',{'reason':'unsupported'}),
      ('describe-edit','/modifier le projet dont le client est Démo Hêtre.','/edit the project whose customer is Démo Hêtre.','search_records',{'resource':'project','client_name':'Démo Hêtre'}),
      ('quote-number','/supprimer le devis 0918/34 après vérification de la fiche.','/delete quote 0918/34 after checking its record.','search_records',{'resource':'quote','query':'0918/34'}),
      ('missing-year','Les encaissements de décembre du projet Verger Essai.','December receipt records for project Verger Essai.','clarify',{'reason':'missing_details'}),
      ('knowledge','Explique comment ajouter une dépense au projet.','Explain how to add an expense to a project.','knowledge',{'query':'add expense to project'}),
    ]
    for key,fr,en,tool,args in fresh:add('independent','fresh-'+key,fr,en,tool,args)
    add('independent','fresh-known','Modifie le client identifiant 1387 : Ville « Larache ».','Update customer ID 1387: City “Larache”.','prepare_change',{'resource':'client','identifier':1387,'operation':'update','changes':{'ville':'Larache'}})
    add('independent','fresh-denied','Supprime la dépense ID 1388.','Delete expense ID 1388.','clarify',{'reason':'unsupported'},capabilities=('read',),switch=True)

    # Compare mutation targets with the real guard, not only generic JSON validity.
    for split,rows in c.splits.items():
        for row in rows:
            expected=row['expected']
            if expected['tool']!='prepare_change':continue
            import json
            context=row.get('trusted_context') or json.loads(row['messages'][0]['content'].rsplit('Trusted context: ',1)[1])
            target={'resource':context.get('current_resource'),'identifier':context.get('current_identifier')}
            args=expected['arguments']
            if not trusted_target(args['resource'],args['identifier'],instruction=row['messages'][-1]['content'],context=target,state={},now=datetime.now(timezone.utc)):
                raise ValueError('Proposal label violates native target provenance: '+row['id'])
    native=Path(__import__('chat_ai.tools',fromlist=['x']).__file__).parent
    c.write(__file__,[native/'tools.py',native/'planner.py',native/'resources.py',native/'targets.py'])
