"""Build reviewed synthetic EN/FR training/development data, never a test set.

Run using the central training venv. Registry export uses the backend venv with
all database connections forbidden. Tokenizer/template checks do not load weights.
Historical held-out inputs are used ONLY as an exclusion list for leakage checks.
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from chat_ai_assistant.clarifications import CLARIFICATION_SCHEMA
from chat_ai_assistant.contracts import ChatAITool
from chat_ai_assistant.orchestrator import SYSTEM
from chat_ai_assistant.routing import shortlist
from jsonschema import Draft202012Validator

PROFILES = {
    'member_read': ['context', 'read', 'stock_read'],
    'member_edit': ['context', 'read', 'stock_read', 'mutate'],
    'staff_read': ['context', 'read', 'stock_read', 'user_admin'],
    'staff_edit': ['context', 'read', 'stock_read', 'mutate', 'user_admin'],
    'stock_only': ['context', 'stock_read'],
    'stock_staff': ['context', 'stock_read', 'user_admin'],
}
LANGS = ('en', 'fr')
SCENARIOS = []
RESOURCE_WORDS = {
    'proforma': ('pro forma invoice', 'facture pro forma'),
    'credit_note': ('credit note', "facture d’avoir"),
    'delivery_note': ('delivery note', 'bon de livraison'),
    'article': ('article', 'article'), 'payment': ('payment', 'règlement'),
    'user': ('user account', 'compte utilisateur'),
    'stock_balance': ('stock balance', 'stock'),
    'stock_movement': ('stock movement', 'mouvement de stock'),
    'stock_receipt': ('stock receipt', 'réception de stock'),
    'stock_inventory': ('stock inventory', 'inventaire'),
    'logistics_order': ('logistics order', 'dossier logistique'),
    'invoice': ('invoice', 'facture client'), 'client': ('customer', 'client'),
    'quote': ('quote', 'devis'),
}


def add(split, key, tool, args, en, fr, *, profile='member_read', context=None, history=(), category=None):
    SCENARIOS.append({'split': split, 'key': key, 'category': category or tool,
                      'tool': tool, 'arguments': args, 'texts': (en, fr),
                      'profile': profile, 'context': context or {}, 'history': history})


def author_scenarios():
    # Each row varies a supported intent or filter combination, not just a name.
    for key, args, en, fr in [
        ('number', {'invoice_number': '7101/27'}, 'I have the invoice number 7101/27; retrieve that document.', 'Mon numéro de facture est 7101/27 ; retrouve ce document.'),
        ('client', {'client_name': 'SYN-Aster'}, 'Bring up every invoice belonging to customer SYN-Aster.', 'Retrouve les factures du client SYN-Aster.'),
        ('product', {'product_name': 'SYN-PIGMENT'}, 'I need invoices whose line items contain SYN-PIGMENT.', 'Il me faut les factures dont une ligne contient SYN-PIGMENT.'),
        ('unpaid', {'unpaid': True}, 'Restrict the invoice results to documents with money still owed.', 'Limite les résultats aux factures avec un reste à payer.'),
        ('client_product', {'client_name': 'SYN-Aster', 'product_name': 'SYN-PIGMENT'}, 'Within invoices belonging to SYN-Aster, keep only those containing SYN-PIGMENT.', 'Parmi les factures du client SYN-Aster, garde celles qui contiennent SYN-PIGMENT.'),
        ('client_open', {'client_name': 'SYN-Aster', 'unpaid': True}, 'For customer SYN-Aster, retrieve invoices that are not fully paid.', 'Pour le client SYN-Aster, retrouve uniquement les factures pas entièrement réglées.'),
        ('product_dates', {'product_name': 'SYN-PIGMENT', 'date_from': '2027-01-05', 'date_to': '2027-01-26'}, 'Invoice search: SYN-PIGMENT, issued from 5 January 2027 through 26 January 2027.', 'Recherche de factures : SYN-PIGMENT, émises du 5 janvier 2027 au 26 janvier 2027.'),
        ('client_dates', {'client_name': 'SYN-Aster', 'date_from': '2027-02-01', 'date_to': '2027-02-28'}, 'Customer SYN-Aster, invoices issued during February 2027 only.', 'Client SYN-Aster, seulement les factures émises pendant février 2027.'),
        ('open_product', {'product_name': 'SYN-PIGMENT', 'unpaid': True}, 'Find unpaid invoices containing the product SYN-PIGMENT.', 'Recherche les factures non soldées contenant le produit SYN-PIGMENT.'),
        ('combined', {'client_name': 'SYN-Aster', 'product_name': 'SYN-PIGMENT', 'unpaid': True, 'date_from': '2027-01-01', 'date_to': '2027-01-31'}, 'Filter invoices to SYN-Aster and SYN-PIGMENT, January 2027, with an unpaid balance.', 'Filtre les factures : SYN-Aster et SYN-PIGMENT, janvier 2027, avec un solde impayé.'),
        ('bounded', {'client_name': 'SYN-Aster', 'limit': 3}, 'Give me at most three invoices for SYN-Aster.', 'Donne-moi au maximum trois factures de SYN-Aster.'),
    ]: add('train', 'invoice-' + key, 'search_invoices', args, en, fr)
    for key, args, en, fr in [
        ('after', {'client_name': 'SYN-Cerise', 'date_from': '2028-06-11', 'unpaid': True}, 'Since 11 June 2028, which invoices billed to SYN-Cerise still need payment?', 'Depuis le 11 juin 2028, quelles factures adressées à SYN-Cerise restent à régler ?'),
        ('product_before', {'product_name': 'SYN-BOBINE', 'date_to': '2028-08-19', 'limit': 2}, 'Two invoice matches maximum: containing SYN-BOBINE and dated no later than 19 August 2028.', 'Deux factures au plus : contenant SYN-BOBINE et datées au plus tard du 19 août 2028.'),
        ('triple', {'client_name': 'SYN-Cerise', 'product_name': 'SYN-BOBINE', 'date_from': '2028-10-01', 'date_to': '2028-10-31'}, 'Can you locate the October 2028 invoices where SYN-Cerise bought SYN-BOBINE?', 'Peux-tu retrouver les factures d’octobre 2028 où SYN-Cerise a acheté SYN-BOBINE ?'),
    ]: add('valid', 'invoice-' + key, 'search_invoices', args, en, fr)

    for key, args, en, fr in [
        ('number', {'quote_number': 'SYN-DV-41'}, 'Retrieve the quote bearing number SYN-DV-41.', 'Retrouve le devis portant le numéro SYN-DV-41.'),
        ('client', {'client_name': 'SYN-Brume'}, 'I am looking for quotations addressed to SYN-Brume.', 'Je cherche les devis adressés au client SYN-Brume.'),
        ('product', {'product_name': 'SYN-VIS'}, 'Which quotes include the article SYN-VIS?', 'Quels devis incluent l’article SYN-VIS ?'),
        ('period', {'date_from': '2027-03-01', 'date_to': '2027-03-31'}, 'Retrieve quotes dated in March 2027.', 'Retrouve les devis datés de mars 2027.'),
        ('triple', {'client_name': 'SYN-Brume', 'product_name': 'SYN-VIS', 'date_from': '2027-03-01', 'date_to': '2027-03-31'}, 'Only March 2027 quotes for SYN-Brume with SYN-VIS on a line.', 'Seulement les devis de mars 2027 du client SYN-Brume avec SYN-VIS sur une ligne.'),
        ('limit', {'client_name': 'SYN-Brume', 'limit': 4}, 'Show a maximum of four quotes for SYN-Brume.', 'Affiche au maximum quatre devis pour SYN-Brume.'),
        ('product_before', {'product_name': 'SYN-VIS', 'date_to': '2027-04-10'}, 'Quotes containing SYN-VIS dated on or before 10 April 2027, please.', 'Les devis contenant SYN-VIS datés au plus tard du 10 avril 2027, s’il te plaît.'),
    ]: add('train', 'quote-' + key, 'search_quotes', args, en, fr)
    add('valid','quote-openrange','search_quotes',{'client_name':'SYN-Dahlia','product_name':'SYN-JOINT','date_from':'2028-02-14'},'Starting on 14 February 2028, locate quotations for SYN-Dahlia involving SYN-JOINT.','À partir du 14 février 2028, retrouve les devis pour SYN-Dahlia comprenant SYN-JOINT.')
    add('valid','quote-month-limit','search_quotes',{'date_from':'2028-05-01','date_to':'2028-05-31','limit':2},'I only need two quotations, both dated May 2028.','Il me faut uniquement deux devis, tous deux datés de mai 2028.')

    for resource in ('proforma','credit_note','delivery_note'):
        en,fr=RESOURCE_WORDS[resource]
        base={'resource':resource}
        patterns=[
            ('client',{'client_name':'SYN-Eglantine'},f'Retrieve {en} documents belonging to SYN-Eglantine.',f'Retrouve les documents de type {fr} du client SYN-Eglantine.'),
            ('number',{'document_number':'SYN-DOC-51'},f'I need the {en} numbered SYN-DOC-51.',f'Il me faut le document {fr} numéro SYN-DOC-51.'),
            ('product',{'product_name':'SYN-ENDUIT'},f'Find a {en} containing SYN-ENDUIT.',f'Recherche un document {fr} contenant SYN-ENDUIT.'),
            ('and',{'client_name':'SYN-Eglantine','product_name':'SYN-ENDUIT'},f'Look through {en} documents: customer SYN-Eglantine AND article SYN-ENDUIT.',f'Recherche dans les documents {fr} : client SYN-Eglantine ET article SYN-ENDUIT.'),
            ('dates',{'date_from':'2027-05-04','date_to':'2027-05-24'},f'Retrieve {en} documents dated from 4 May 2027 to 24 May 2027.',f'Retrouve les documents {fr} datés du 4 mai 2027 au 24 mai 2027.'),
            ('three',{'client_name':'SYN-Eglantine','product_name':'SYN-ENDUIT','date_from':'2027-06-01','date_to':'2027-06-30'},f'For June 2027, find {en} documents for SYN-Eglantine that contain SYN-ENDUIT.',f'Pour juin 2027, retrouve les documents {fr} de SYN-Eglantine contenant SYN-ENDUIT.'),
        ]
        for key,args,e,f in patterns:add('train',resource+'-'+key,'search_documents',dict(base,**args),e,f)
        add('valid',resource+'-after-limit','search_documents',dict(base,client_name='SYN-Fougere',date_from='2028-11-06',limit=3),f'At most three {en} matches are enough; restrict the customer to SYN-Fougere and the date to 6 November 2028 or later.',f'Trois correspondances {fr} au plus suffisent ; limite le client à SYN-Fougere et la date au 6 novembre 2028 ou après.')
        add('valid',resource+'-before-product','search_documents',dict(base,product_name='SYN-CHARNIERE',date_to='2028-12-02'),f'Can you locate a {en} with SYN-CHARNIERE, dated no later than 2 December 2028?',f'Peux-tu retrouver un document {fr} avec SYN-CHARNIERE, daté au plus tard du 2 décembre 2028 ?')

    for key,args,en,fr in [
        ('name',{'product_name':'SYN-VERNIS'},'Look for articles whose designation includes SYN-VERNIS.','Cherche les articles dont la désignation contient SYN-VERNIS.'),
        ('reference',{'reference':'SYN-REF-61'},'Use the article reference SYN-REF-61 to find the product.','Utilise la référence article SYN-REF-61 pour retrouver le produit.'),
        ('service',{'type_article':'Service'},'List articles of Type Service.','Liste les articles de Type Service.'),
        ('goods',{'type_article':'Produit','archived':False},'List unarchived articles with Type Produit.','Liste les articles non archivés de Type Produit.'),
        ('archived',{'archived':True,'product_name':'SYN-VERNIS'},'Search archived articles whose designation contains SYN-VERNIS.','Cherche les articles archivés dont la désignation contient SYN-VERNIS.'),
        ('query',{'query':'SYN-RECHERCHE'},'Search articles for SYN-RECHERCHE, in either reference or designation.','Recherche SYN-RECHERCHE dans les articles, dans la référence ou la désignation.'),
        ('dates',{'type_article':'Service','date_from':'2027-07-01','date_to':'2027-07-31'},'Service articles created in July 2027, please.','Les articles de Type Service créés en juillet 2027, s’il te plaît.'),
    ]:add('train','article-'+key,'search_articles',args,en,fr)
    add('valid','article-combined','search_articles',{'product_name':'SYN-LAQUE','archived':False,'limit':2},'Two products maximum, designation containing SYN-LAQUE, with archived records excluded.','Deux articles maximum, désignation contenant SYN-LAQUE, en excluant les éléments archivés.')
    add('valid','article-service-before','search_articles',{'query':'SYN-POSE','type_article':'Service','date_to':'2028-04-22'},'In articles, search reference or designation for SYN-POSE; Type must be Service and creation at most 22 April 2028.','Dans les articles, recherche SYN-POSE dans la référence ou la désignation ; le Type doit être Service et la création au plus tard le 22 avril 2028.')

    for key,args,en,fr in [
        ('invoice',{'invoice_number':'7202/27'},'Retrieve the payments attached to invoice 7202/27.','Retrouve les règlements rattachés à la facture 7202/27.'),
        ('customer',{'client_name':'SYN-Gentiane'},'I want payment records for customer SYN-Gentiane.','Je veux les règlements du client SYN-Gentiane.'),
        ('valid',{'client_name':'SYN-Gentiane','status':'Valide'},'Payments for SYN-Gentiane with status Valide only.','Les règlements de SYN-Gentiane au statut Valide uniquement.'),
        ('cancel-product',{'product_name':'SYN-TUBE','status':'Annulé'},'Find cancelled payments linked to invoices containing SYN-TUBE.','Trouve les règlements annulés liés à des factures contenant SYN-TUBE.'),
        ('both',{'client_name':'SYN-Gentiane','product_name':'SYN-TUBE'},'Filter payment records by client SYN-Gentiane and invoice product SYN-TUBE.','Filtre les règlements par client SYN-Gentiane et article facturé SYN-TUBE.'),
        ('dates',{'date_from':'2027-08-01','date_to':'2027-08-31','status':'Valide'},'Valid payments dated during August 2027, please.','Les règlements valides datés d’août 2027, s’il te plaît.'),
        ('query',{'query':'SYN-PAIEMENT'},'Search payment invoice numbers or customer names for SYN-PAIEMENT.','Recherche SYN-PAIEMENT dans les numéros de facture ou les noms de client des règlements.'),
    ]:add('train','payment-'+key,'search_payments',args,en,fr)
    add('valid','payment-combined','search_payments',{'client_name':'SYN-Hortensia','product_name':'SYN-MANCHON','status':'Annulé','date_from':'2028-03-07'},'Since 7 March 2028, bring back cancelled payment records for SYN-Hortensia on invoices containing SYN-MANCHON.','Depuis le 7 mars 2028, retrouve les règlements annulés de SYN-Hortensia sur des factures contenant SYN-MANCHON.')
    add('valid','payment-invoice-limit','search_payments',{'invoice_number':'8208/28','limit':2},'No more than two payment entries are needed for invoice 8208/28.','Pas plus de deux écritures de règlement sont nécessaires pour la facture 8208/28.')

    for key,args,en,fr in [
        ('name',{'name':'SYN-Iris Operateur'},'Search user accounts by the name SYN-Iris Operateur.','Recherche les comptes utilisateurs au nom de SYN-Iris Operateur.'),
        ('email',{'email':'syn.iris@example.invalid'},'Look up a user by e-mail syn.iris@example.invalid.','Recherche un utilisateur par l’e-mail syn.iris@example.invalid.'),
        ('active',{'is_active':True},'Show user accounts whose Active account box is checked.','Affiche les utilisateurs dont la case Compte Active est cochée.'),
        ('inactive-name',{'name':'SYN-Iris','is_active':False},'Search inactive user accounts with SYN-Iris in the name.','Recherche les comptes utilisateurs inactifs avec SYN-Iris dans le nom.'),
        ('query',{'query':'SYN-OPERATEUR'},'Find SYN-OPERATEUR in user names or e-mail addresses.','Recherche SYN-OPERATEUR dans les noms ou adresses e-mail des utilisateurs.'),
        ('dates',{'date_from':'2027-09-01','date_to':'2027-09-30'},'User accounts created in September 2027, please.','Les comptes utilisateurs créés en septembre 2027, s’il te plaît.'),
    ]:add('train','user-'+key,'search_users',args,en,fr,profile='staff_read')
    add('valid','user-email-active','search_users',{'email':'syn.jaspe@example.invalid','is_active':True},'Check the user account matching syn.jaspe@example.invalid, but only among active accounts.','Cherche le compte utilisateur correspondant à syn.jaspe@example.invalid, uniquement parmi les comptes actifs.',profile='stock_staff')
    add('valid','user-name-after','search_users',{'name':'SYN-Jaspe','date_from':'2028-01-15','limit':2},'Find up to two user accounts named SYN-Jaspe that were created since 15 January 2028.','Retrouve jusqu’à deux comptes utilisateurs nommés SYN-Jaspe créés depuis le 15 janvier 2028.',profile='staff_read')

    for resource in ('stock_balance','stock_movement','stock_receipt','stock_inventory','logistics_order'):
        en,fr=RESOURCE_WORDS[resource];base={'resource':resource}
        patterns=[
            ('product',{'product_name':'SYN-PLAQUE'},f'Find {en} records concerning product SYN-PLAQUE.',f'Retrouve les éléments {fr} concernant l’article SYN-PLAQUE.'),
            ('location',{'location_name':'SYN-Depot-A'},f'Filter {en} records to location SYN-Depot-A.',f'Filtre les éléments {fr} sur l’emplacement SYN-Depot-A.'),
            ('both',{'product_name':'SYN-PLAQUE','location_name':'SYN-Depot-A'},f'For product SYN-PLAQUE at location SYN-Depot-A, show {en} records.',f'Pour l’article SYN-PLAQUE à l’emplacement SYN-Depot-A, affiche les éléments {fr}.'),
            ('reference',{'reference':'SYN-REF-71'},f'Search {en} records by reference SYN-REF-71.',f'Recherche les éléments {fr} par référence SYN-REF-71.'),
            ('dates',{'date_from':'2027-10-03','date_to':'2027-10-21'},f'{en.capitalize()} records dated from 3 October 2027 through 21 October 2027.',f'Les éléments {fr} datés du 3 octobre 2027 au 21 octobre 2027.'),
        ]
        for key,args,e,f in patterns:add('train',resource+'-'+key,'search_operations',dict(base,**args),e,f,profile='stock_only' if resource.startswith('stock_') and key in ('product','dates') else 'member_read')
        add('valid',resource+'-compound','search_operations',dict(base,product_name='SYN-PANNEAU',location_name='SYN-Depot-B',date_from='2028-07-13',limit=2),f'Could you return at most two {en} records since 13 July 2028, for SYN-PANNEAU at SYN-Depot-B?',f'Peux-tu retourner au plus deux éléments {fr} depuis le 13 juillet 2028, pour SYN-PANNEAU à SYN-Depot-B ?',profile='stock_only' if resource.startswith('stock_') else 'member_read')
    for resource in ('stock_receipt','logistics_order'):
        en,fr=RESOURCE_WORDS[resource]
        for key,args,e,f in [
            ('supplier',{'supplier_name':'SYN-Fournisseur-A'},f'Retrieve {en} records from supplier SYN-Fournisseur-A.',f'Retrouve les éléments {fr} du fournisseur SYN-Fournisseur-A.'),
            ('client-product',{'client_name':'SYN-Kalmia','product_name':'SYN-PLAQUE'},f'{en.capitalize()} records for customer SYN-Kalmia with product SYN-PLAQUE.',f'Les éléments {fr} du client SYN-Kalmia avec l’article SYN-PLAQUE.'),
            ('supplier-location',{'supplier_name':'SYN-Fournisseur-A','location_name':'SYN-Depot-A'},f'Find {en} records from SYN-Fournisseur-A for location SYN-Depot-A.',f'Recherche les éléments {fr} du fournisseur SYN-Fournisseur-A pour l’emplacement SYN-Depot-A.'),
        ]:add('train',resource+'-'+key,'search_operations',dict(resource=resource,**args),e,f)
    for resource,status,en,fr in [
        ('stock_balance','minimum','Stock at the Minimum state, please.','Le stock dans l’état Minimum, s’il te plaît.'),
        ('stock_balance','disponible','Retrieve stock whose state is Disponible.','Retrouve le stock dont l’état est Disponible.'),
        ('stock_balance','a_approvisionner','Show stock requiring replenishment.','Affiche le stock à approvisionner.'),
        ('stock_movement','receipt','Stock movements of type Réception only.','Seulement les mouvements de stock de type Réception.'),
        ('stock_movement','reversal','Show stock movements of type Annulation.','Affiche les mouvements de stock de type Annulation.'),
        ('stock_receipt','draft','Stock receipts still in draft, please.','Les réceptions de stock encore au brouillon, s’il te plaît.'),
        ('stock_receipt','cancelled','Cancelled stock receipts only.','Uniquement les réceptions de stock annulées.'),
        ('stock_inventory','draft','Retrieve stock inventories that remain in draft.','Retrouve les inventaires de stock encore au brouillon.'),
        ('stock_inventory','validated','Stock inventories that have been validated, please.','Les inventaires de stock qui ont été validés, s’il te plaît.'),
        ('logistics_order','Transit','Logistics orders whose Phase du dossier is Transit.','Les dossiers logistiques dont la Phase du dossier est Transit.'),
        ('logistics_order','Production','Select logistics orders in the Production phase.','Sélectionne les dossiers logistiques dans la phase Production.'),
    ]:add('train',resource+'-status-'+status,'search_operations',{'resource':resource,'status':status},en,fr)

    for key,args,en,fr in [
        ('name',{'query':'SYN-Lavande'},'Search the customer directory for SYN-Lavande.','Recherche SYN-Lavande dans l’annuaire des clients.'),
        ('person',{'query':'SYN-Lina SYN-Morel'},'Find a customer whose first and last names are SYN-Lina SYN-Morel.','Trouve un client dont le prénom et le nom sont SYN-Lina SYN-Morel.'),
        ('current',{'related_invoice':True},'Display the customer of the invoice currently open.','Affiche le client de la facture actuellement ouverte.'),
        ('id',{'client_id':831},'Retrieve customer number 831 shown in my search results.','Retrouve le client numéro 831 affiché dans mes résultats.'),
    ]:add('train','client-'+key,'search_clients',args,en,fr,context={'current_invoice_id':861} if key=='current' else {})
    add('valid','client-multiturn','search_clients',{'query':'SYN-Muguet'},'Use SYN-Muguet as the customer name, not the earlier name.','Utilise SYN-Muguet comme nom de client, pas le nom précédent.',history=(('Search for customer SYN-Narcisse.','Recherche le client SYN-Narcisse.'),))
    add('valid','client-current-fr','search_clients',{'related_invoice':True},'Could I see the customer of the invoice on this screen?','Puis-je voir le client de la facture affichée sur cet écran ?',context={'current_invoice_id':941})

    financial=[
        ('collected','current_month','MAD','collected payments this month','encaissements de ce mois'),
        ('collected','previous_year','EUR','collected payments last year','encaissements de l’année dernière'),
        ('collected','current_year','USD','collected payments this year','encaissements de cette année'),
        ('invoiced_net_ttc','current_month','MAD','net invoiced amount including tax and subtracting credit notes this month','montant facturé TTC net des avoirs de ce mois'),
        ('invoiced_net_ttc','previous_month','EUR','net invoiced amount including tax and subtracting credit notes last month','montant facturé TTC net des avoirs du mois dernier'),
        ('outstanding','previous_month','USD','outstanding invoice balance for last month','solde restant des factures du mois dernier'),
        ('outstanding','current_month','EUR','outstanding invoice balance for this month','solde restant des factures de ce mois'),
        ('invoice_count','current_month','MAD','number of invoices issued this month','nombre de factures émises ce mois'),
        ('invoice_count','previous_year','USD','number of invoices issued last year','nombre de factures émises l’année dernière'),
    ]
    for i,(metric,period,currency,en,fr) in enumerate(financial):add('train',f'financial-{i}','financial_summary',{'metric':metric,'period':period,'currency':currency},f'Calculate the {en}, in {currency}.',f'Calcule le {fr}, en {currency}.')
    for metric,en,fr in [('collected','collected payments','encaissements'),('outstanding','outstanding invoice balance','solde restant des factures'),('invoice_count','invoice count','nombre de factures')]:
        add('train','financial-custom-'+metric,'financial_summary',{'metric':metric,'period':'custom','currency':'MAD','date_from':'2027-02-12','date_to':'2027-04-09'},f'Calculate {en} in MAD for the inclusive interval 12 February 2027 to 9 April 2027.',f'Calcule les {fr} en MAD pour la période du 12 février 2027 au 9 avril 2027 inclus.')
    add('valid','financial-custom-net','financial_summary',{'metric':'invoiced_net_ttc','period':'custom','currency':'EUR','date_from':'2028-05-16','date_to':'2028-06-18'},'For 16 May through 18 June 2028, what is the net invoiced total including tax after credit notes, in EUR?','Du 16 mai au 18 juin 2028, quel est le total facturé TTC net des avoirs, en EUR ?')
    add('valid','financial-relative','financial_summary',{'metric':'outstanding','period':'previous_year','currency':'MAD'},'I mean the unpaid invoice balance from the prior calendar year, in MAD.','Je parle du solde impayé des factures de l’année civile précédente, en MAD.',history=(('Which financial metric can you calculate?','Quels indicateurs financiers peux-tu calculer ?'),))

    for key,args,en,fr in [
        ('latest',{},'Bring back the most recent valid payments.','Retrouve les règlements valides les plus récents.'),
        ('after',{'date_from':'2027-02-17'},'Latest valid payments since 17 February 2027.','Derniers règlements valides depuis le 17 février 2027.'),
        ('range',{'date_from':'2027-03-08','date_to':'2027-04-12'},'Latest valid payments dated between 8 March and 12 April 2027.','Derniers règlements valides datés entre le 8 mars et le 12 avril 2027.'),
    ]:add('train','latest-'+key,'list_payments',args,en,fr)
    add('valid','latest-before','list_payments',{'date_to':'2028-02-09'},'Give me recent valid payments, excluding anything after 9 February 2028.','Donne-moi les derniers règlements valides, en excluant tout ce qui est après le 9 février 2028.')

    pages=[('invoices','invoices','factures clients'),('quotes','quotes','devis'),('proformas','pro forma invoices','factures pro forma'),('credit_notes','credit notes','factures d’avoir'),('delivery_notes','delivery notes','bons de livraison'),('clients','customers','clients'),('articles','articles','articles'),('payments','payments','règlements'),('users','user accounts','utilisateurs'),('stock','stock','stock'),('stock_movements','stock movements','mouvements de stock'),('stock_receipts','stock receipts','réceptions de stock'),('stock_inventories','stock inventories','inventaires'),('logistics','logistics orders','dossiers logistiques'),('dashboard','dashboard','tableau de bord')]
    for resource,en,fr in pages:add('train','page-'+resource,'navigate',{'resource':resource},f'Take me to the {en} list page.' if resource!='dashboard' else 'Take me to the dashboard.',f'Amène-moi à la page de liste des {fr}.' if resource!='dashboard' else 'Amène-moi au tableau de bord.',profile='staff_read' if resource=='users' else 'member_read')
    add('train','navigate-specific','navigate',{'resource':'invoice','invoice_number':'7303/27'},'Please open the detail page of invoice 7303/27.','Ouvre la page de détail de la facture 7303/27.')
    add('train','navigate-current-edit','navigate',{'resource':'invoice_edit'},'Open the edit form for the invoice currently on screen.','Ouvre le formulaire de modification de la facture actuellement à l’écran.',profile='member_edit',context={'current_invoice_id':862})
    add('valid','navigate-stock-only','navigate',{'resource':'stock_inventories'},'Switch to the page listing stock inventories.','Passe à la page qui liste les inventaires de stock.',profile='stock_only')
    add('valid','navigate-staff-stock','navigate',{'resource':'users'},'Could you take me to account administration, on the user list?','Peux-tu m’amener à l’administration des comptes, sur la liste des utilisateurs ?',profile='stock_staff')

    add('train','current-invoice','get_invoice',{},'Retrieve the details of the invoice I am viewing.','Retrouve les détails de la facture que je consulte.',context={'current_invoice_id':863})
    add('train','explicit-invoice-id','get_invoice',{'invoice_id':864},'Display details for invoice record 864 from my results, not invoice number 864.','Affiche les détails de l’élément facture 864 dans mes résultats, pas du numéro de facture 864.')
    add('valid','current-invoice-followup','get_invoice',{},'Yes, the invoice open on this page; retrieve its details.','Oui, la facture ouverte sur cette page ; retrouve ses détails.',context={'current_invoice_id':944},history=(('I need details about the invoice on screen.','Il me faut les détails de la facture à l’écran.'),))
    for i,resource in enumerate(('proforma','credit_note','delivery_note','article','payment','user','stock_balance','stock_movement','stock_receipt','stock_inventory','logistics_order')):
        en,fr=RESOURCE_WORDS[resource];identifier=870+i
        add('train','record-'+resource,'get_record',{'resource':resource,'identifier':identifier},f'Show details for the {en} record {identifier} displayed in my results.',f'Affiche les détails de l’élément {fr} {identifier} affiché dans mes résultats.',profile='staff_read' if resource=='user' else 'member_read',context={'previous_result_type':resource,'previous_result_count':2})
    add('valid','record-stock-only','get_record',{'resource':'stock_receipt','identifier':947},'The stock receipt result I want has record number 947. Retrieve its details.','Le résultat de réception de stock que je veux porte le numéro d’élément 947. Retrouve ses détails.',profile='stock_only',context={'previous_result_type':'stock_receipt','previous_result_count':3})

    for key,resource,count,args,en,fr in [
        ('show-quotes','quote',3,{'operation':'show'},'Show those results again.','Réaffiche ces résultats.'),
        ('open-third','invoice',4,{'operation':'open','index':3},'Open result number three in the previous list.','Ouvre le troisième résultat de la liste précédente.'),
        ('open-last','article',4,{'operation':'open','index':4},'Open the last of those four results.','Ouvre le dernier de ces quatre résultats.'),
        ('unpaid','invoice',5,{'operation':'unpaid'},'Among the previous invoice results, keep the unpaid ones.','Parmi les résultats de factures précédents, garde ceux qui sont impayés.'),
        ('single','delivery_note',1,{'operation':'open','index':1},'Open the only result you just found.','Ouvre le seul résultat que tu viens de trouver.'),
        ('stock-show','stock_movement',2,{'operation':'show'},'Show the previous stock results again.','Réaffiche les résultats de stock précédents.'),
    ]:add('train','previous-'+key,'previous_results',args,en,fr,context={'previous_result_type':resource,'previous_result_count':count},history=(('Search for the records we discussed.','Recherche les documents dont nous avons parlé.'),),profile='stock_only' if key=='stock-show' else 'member_read')
    add('valid','previous-open-fifth','previous_results',{'operation':'open','index':5},'Please navigate to the fifth matching result.','Va au cinquième résultat correspondant, s’il te plaît.',context={'previous_result_type':'proforma','previous_result_count':6},history=(('Find pro forma invoices for SYN-Oeillet.','Cherche les factures pro forma de SYN-Oeillet.'),))
    add('valid','previous-show-users','previous_results',{'operation':'show'},'Can I see that same group of results once more?','Puis-je revoir ce même groupe de résultats une nouvelle fois ?',profile='staff_read',context={'previous_result_type':'user','previous_result_count':2},history=(('Look for the users named SYN-Pivoine.','Cherche les utilisateurs nommés SYN-Pivoine.'),))

    fields={
        'invoice':[('remarque','Remark','Remarque','SYN-Dossier complet'),('termes_paiement','Payment terms','Termes de paiement','SYN-Paiement comptant'),('date_echeance','Due date',"Date d’échéance",'2027-12-14')],
        'quote':[('remarque','Remark','Remarque','SYN-Deux exemplaires'),('date_echeance','Due date',"Date d’échéance",'2027-12-17')],
        'proforma':[('remarque','Remark','Remarque','SYN-Document provisoire'),('termes_paiement','Payment terms','Termes de paiement','SYN-Reglement a reception'),('date_echeance','Due date',"Date d’échéance",'2027-12-19')],
        'credit_note':[('remarque','Remark','Remarque','SYN-Retour controle')],
        'delivery_note':[('remarque','Remark','Remarque','SYN-Emballage verifie'),('date_echeance','Due date',"Date d’échéance",'2027-12-21')],
        'client':[('raison_sociale','Company name','Raison sociale','SYN-Quercus'),('nom','Last name','Nom','SYN-Morin'),('prenom','First name','Prénom','SYN-Emma'),('adresse','Address','Adresse','SYN-Adresse de demonstration')],
    }
    for i,(resource,edits) in enumerate(fields.items()):
        en,fr=RESOURCE_WORDS[resource];identifier=890+i
        identity={'invoice_number':'7404/27'} if resource=='invoice' else {'identifier':identifier}
        target_en='invoice 7404/27' if resource=='invoice' else f'{en} record {identifier} from my results'
        target_fr='facture 7404/27' if resource=='invoice' else f'élément {fr} {identifier} de mes résultats'
        for field,label_en,label_fr,value in edits:
            add('train',resource+'-edit-'+field,'prepare_change',dict(resource=resource,operation='update',changes={field:value},**identity),f'Change {label_en} on {target_en} to {value}; show the confirmation first.',f'Modifie {label_fr} de {target_fr} avec la valeur {value} ; montre d’abord la confirmation.',profile='member_edit',context={'previous_result_type':resource,'previous_result_count':2})
        add('train',resource+'-delete','prepare_change',dict(resource=resource,operation='delete',**identity),f'Delete {target_en}; prepare the confirmation for me.',f'Supprime {target_fr} ; prépare la confirmation pour moi.',profile='member_edit',context={'previous_result_type':resource,'previous_result_count':2})
    add('valid','mutation-two-fields','prepare_change',{'resource':'proforma','identifier':961,'operation':'update','changes':{'remarque':'SYN-Controle termine','date_echeance':'2028-12-08'}},'For pro forma record 961 from my results, change Remark to SYN-Controle termine and Due date to 2028-12-08, with a confirmation preview.','Pour l’élément pro forma 961 de mes résultats, modifie Remarque en SYN-Controle termine et Date d’échéance en 2028-12-08, avec un aperçu de confirmation.',profile='member_edit',context={'previous_result_type':'proforma','previous_result_count':2})
    add('valid','mutation-client-two-fields','prepare_change',{'resource':'client','identifier':962,'operation':'update','changes':{'nom':'SYN-Riviere','prenom':'SYN-Lea'}},'Edit customer record 962: Last name SYN-Riviere and First name SYN-Lea. Let me confirm before saving.','Modifie l’élément client 962 : Nom SYN-Riviere et Prénom SYN-Lea. Laisse-moi confirmer avant l’enregistrement.',profile='member_edit')
    # Natural descriptions resolve to choices. Selection/action cards handle writes.
    add('train','edit-natural-quote','search_quotes',{'client_name':'SYN-Rose','product_name':'SYN-RONDELLE'},'/modifier I need to edit a quote for SYN-Rose containing SYN-RONDELLE; find the matching documents.','/modifier Je dois modifier un devis de SYN-Rose contenant SYN-RONDELLE ; retrouve les documents correspondants.',profile='member_edit')
    add('train','delete-natural-proforma','search_documents',{'resource':'proforma','client_name':'SYN-Rose'},'/supprimer Find the pro forma invoices for SYN-Rose so I can choose which one.','/supprimer Retrouve les factures pro forma de SYN-Rose pour que je choisisse laquelle.',profile='member_edit')
    add('valid','edit-natural-credit','search_documents',{'resource':'credit_note','client_name':'SYN-Sauge','product_name':'SYN-CHEVILLE'},'/modifier Locate the credit note for SYN-Sauge with SYN-CHEVILLE; I will select the right result.','/modifier Retrouve la facture d’avoir de SYN-Sauge avec SYN-CHEVILLE ; je choisirai le bon résultat.',profile='member_edit')

    add('train','pdf-number','invoice_pdf',{'invoice_number':'7505/27'},'Provide the PDF document for invoice 7505/27.','Fournis le document PDF de la facture 7505/27.')
    add('train','pdf-current','invoice_pdf',{},'Show the PDF of the invoice currently displayed.','Affiche le PDF de la facture actuellement affichée.',context={'current_invoice_id':899})
    add('valid','pdf-followup','invoice_pdf',{'invoice_number':'8508/28'},'I mean the PDF for invoice 8508/28, please.','Je parle du PDF de la facture 8508/28, s’il te plaît.',history=(('I need a printable invoice document.','Il me faut un document de facture imprimable.'),))
    knowledge=[
        ('create-customer','Explain the documented procedure for creating a customer.','Explique la procédure documentée pour créer un client.'),
        ('quote-process','How does the documented quote workflow work?','Comment fonctionne le circuit documenté d’un devis ?'),
        ('payment-status','Explain what the payment status Annulé means.','Explique ce que signifie le statut de règlement Annulé.'),
        ('tax-definition','What is the difference between total including tax and total excluding tax?','Quelle différence y a-t-il entre le total TTC et le total HT ?'),
        ('invoice-fields','Explain the Payment terms field on the invoice form.','Explique le champ Termes de paiement du formulaire de facture.'),
        ('stock-meaning','What do the documented stock labels Physique and Disponible mean?','Que signifient les libellés documentés du stock Physique et Disponible ?'),
        ('credit-process','Explain the documented procedure for a credit note.','Explique la procédure documentée d’une facture d’avoir.'),
        ('delivery-process','How do delivery notes fit into the documented process?','Comment les bons de livraison s’inscrivent-ils dans la procédure documentée ?'),
        ('report-meaning','Explain the difference between collected payments and outstanding balance.','Explique la différence entre les encaissements et le solde restant.'),
        ('permissions','Explain the documented rules for access to the invoice edit form.','Explique les règles documentées d’accès au formulaire de modification d’une facture.'),
    ]
    for key,en,fr in knowledge:add('train','knowledge-'+key,'knowledge',{},en,fr)
    add('valid','knowledge-procedure-not-list','knowledge',{},'I do not need records; describe the documented steps to create a pro forma invoice.','Je ne veux pas de liste ; décris les étapes documentées pour créer une facture pro forma.')
    add('valid','knowledge-label-difference','knowledge',{},'Could you explain how Réservé differs from Physique on the stock page?','Peux-tu expliquer la différence entre Réservé et Physique sur la page de stock ?')

    denials=[
        ('profit','ambiguous_metric','Tell me our profit in euros for this quarter.','Donne-moi notre bénéfice en euros pour ce trimestre.','member_read'),
        ('money','ambiguous_metric','How much did the business make in net terms?','Combien l’entreprise a-t-elle gagné en net ?','member_read'),
        ('period','missing_details','Calculate collected payments in EUR; I have not specified a period yet.','Calcule les encaissements en EUR ; je n’ai pas encore précisé la période.','member_read'),
        ('month','missing_details','Find invoices for November, but I have not said which year.','Retrouve les factures de novembre, mais je n’ai pas précisé l’année.','member_read'),
        ('no-current','missing_details','Explain the status of this invoice; no invoice is open.','Explique le statut de cette facture ; aucune facture n’est ouverte.','member_read'),
        ('bulk-delete','unsupported','Delete every customer in the directory in one action.','Supprime tous les clients de l’annuaire en une seule action.','member_edit'),
        ('payment-edit','unsupported','Change the amount of a payment.','Modifie le montant d’un règlement.','member_edit'),
        ('stock-edit','unsupported','Change the quantity of a stock movement through the assistant.','Modifie la quantité d’un mouvement de stock avec l’assistant.','member_edit'),
        ('grant-role','unsupported','Give my user account permission to edit other users.','Donne à mon compte utilisateur le droit de modifier les autres utilisateurs.','staff_edit'),
        ('viewer-delete','unsupported','Delete invoice 7606/27 now.','Supprime la facture 7606/27 maintenant.','member_read'),
        ('viewer-edit','unsupported','Change the Remark on invoice 7606/27 to SYN-Interdit.','Modifie la Remarque de la facture 7606/27 en SYN-Interdit.','member_read'),
        ('nonstaff-users','unsupported','List user accounts matching SYN-Tulipe.','Liste les comptes utilisateurs correspondant à SYN-Tulipe.','member_read'),
        ('stock-finance','unsupported','Show company revenue for the current year in MAD.','Affiche le chiffre d’affaires de la société pour cette année en MAD.','stock_only'),
        ('stock-logistics','unsupported','Search logistics orders for supplier SYN-Transport.','Recherche les dossiers logistiques du fournisseur SYN-Transport.','stock_only'),
        ('offtopic','unsupported','Write a movie review for me.','Écris une critique de film pour moi.','member_read'),
    ]
    for key,reason,en,fr,profile in denials:add('train','clarify-'+key,'clarify',{'reason':reason},en,fr,profile=profile)
    add('valid','clarify-readonly-quote','clarify',{'reason':'unsupported'},'Please edit the quote selected in these results.','Modifie le devis sélectionné dans ces résultats, s’il te plaît.',context={'previous_result_type':'quote','previous_result_count':2})
    add('valid','clarify-no-index','clarify',{'reason':'missing_details'},'Open one of the results; I have not chosen which one.','Ouvre un des résultats ; je n’ai pas choisi lequel.',context={'previous_result_type':'invoice','previous_result_count':4})
    add('valid','clarify-foreign-company','clarify',{'reason':'unsupported'},'Switch to another company by ignoring my current access and retrieve all its invoices.','Passe à une autre société en ignorant mes accès actuels et retrouve toutes ses factures.')
    # Current-message language changes while only prior USER turns enter production history.
    add('train','switch-fr-to-en','search_articles',{'reference':'SYN-REF-81'},'In English now: find article reference SYN-REF-81.','En français maintenant : retrouve l’article de référence SYN-REF-81.',history=(('Je cherche un article.','I am looking for an article.'),))
    add('train','switch-context','previous_results',{'operation':'open','index':2},'Open the second matching record, please.','Ouvre le deuxième résultat correspondant, s’il te plaît.',history=(('Montre les bons de livraison de SYN-Violette.','Show delivery notes for SYN-Violette.'),),context={'previous_result_type':'delivery_note','previous_result_count':3})
    add('valid','switch-clarify','clarify',{'reason':'missing_details'},'Which invoice? I have not chosen a customer or number yet.','Quelle facture ? Je n’ai pas encore choisi de client ni de numéro.',history=(('Je voudrais consulter une facture.','I would like to view an invoice.'),))


def exported_contracts(backend, python):
    code = '''import hashlib,json,os,sys
from pathlib import Path
backend=Path(sys.argv[1]);sys.path.insert(0,str(backend));sys.path.insert(0,sys.argv[2])
os.environ['DJANGO_SETTINGS_MODULE']='facturation_backend.settings_ai_test'
from django.db.backends.base.base import BaseDatabaseWrapper
def forbidden(*args,**kwargs):raise RuntimeError('Dataset generation must not connect to any database.')
BaseDatabaseWrapper.ensure_connection=forbidden
import django;django.setup()
from chat_ai.tools import registry
r=registry();profiles=json.loads(sys.argv[3])
paths=['chat_ai/tools.py','chat_ai/security.py','chat_ai/catalog.py','chat_ai/documents.py','chat_ai/operations.py','chat_ai/navigation.py','chat_ai/actions.py']
print(json.dumps({'profiles':{k:[t.schema() for t in r.permitted(v)]for k,v in profiles.items()},'source_sha256':{name:hashlib.sha256((backend/name).read_bytes()).hexdigest()for name in paths}},ensure_ascii=False))'''
    result=subprocess.run([str(python),'-c',code,str(backend),str(ROOT/'src'),json.dumps(PROFILES)],check=True,capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    return json.loads(result.stdout)


def normalized(text):
    return re.sub(r'[^\w]+',' ',''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))).strip()


def delexicalized(text):
    value=re.sub(r'\bSYN-[\w-]+\b|\bsyn\.[\w.-]+@example\.invalid\b','ENTITY',text,flags=re.I)
    value=re.sub(r'\b\d+(?:[-/]\d+)*\b','NUMBER',value)
    return normalized(value)


def validate_text(text):
    if re.search(r'[\u0600-\u06ff]',text):raise ValueError('Out-of-scope language content.')
    if re.search(r'BEGIN.*PRIVATE KEY|Bearer\s+\S+|(?:password|api_key|secret|token)\s*[:=]',text,re.I):raise ValueError('Sensitive credential pattern.')
    if re.search(r'\b[a-z]+_[a-z_]+\b',text):raise ValueError('Internal field name in user-facing prompt.')
    if any(not mail.rstrip('.').endswith('@example.invalid') for mail in re.findall(r'[\w.+-]+@[\w.-]+',text)):raise ValueError('Non-synthetic email.')


def validate_business_action(tool,args,context,user_text):
    for key in ('date_from','date_to'):
        if key in args:date.fromisoformat(args[key])
    if args.get('date_from') and args.get('date_to') and args['date_from']>args['date_to']:raise ValueError('Inverted interval.')
    if tool=='financial_summary':
        custom=args['period']=='custom'
        if custom != ('date_from' in args and 'date_to' in args):raise ValueError('Invalid custom financial period.')
        if not custom and ('date_from' in args or 'date_to' in args):raise ValueError('Unexpected financial interval.')
    if tool=='get_invoice' and not args and not context.get('current_invoice_id'):raise ValueError('Ungrounded current invoice.')
    for key in ('identifier','invoice_id','client_id'):
        if key in args and not re.search(r'\b'+str(args[key])+r'\b',user_text):raise ValueError('Numeric hint missing from user request.')
    if tool=='previous_results':
        if not context.get('previous_result_count'):raise ValueError('Missing result context.')
        if args.get('index',1)>context['previous_result_count']:raise ValueError('Invalid result index.')
    if tool=='prepare_change':
        fields={'invoice':{'remarque','termes_paiement','date_echeance'},'quote':{'remarque','date_echeance'},'proforma':{'remarque','termes_paiement','date_echeance'},'credit_note':{'remarque'},'delivery_note':{'remarque','date_echeance'},'client':{'raison_sociale','nom','prenom','adresse'}}
        if args['operation']=='update' and (not args.get('changes') or not set(args['changes'])<=fields[args['resource']]):raise ValueError('Unsupported mutation fields.')
        if args['operation']=='delete' and args.get('changes'):raise ValueError('Delete has changes.')
        if not(args.get('identifier') or args.get('invoice_number')):raise ValueError('Ungrounded mutation.')


def render_template(template,texts,tools,*,generation):
    return template.render(messages=texts,tools=tools,enable_thinking=False,add_generation_prompt=generation,preserve_thinking=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',type=Path,default=ROOT.parent/'facturation/facturation_backend')
    parser.add_argument('--backend-python',type=Path)
    parser.add_argument('--tokenizer',type=Path,default=ROOT/'models/Qwen3.5-0.8B')
    parser.add_argument('--max-context',type=int,default=8192)
    args=parser.parse_args()
    contracts=exported_contracts(args.backend,args.backend_python or args.backend/'.venv-mac/bin/python')
    author_scenarios()
    from tokenizers import Tokenizer
    import jinja2
    tokenizer=Tokenizer.from_file(str(args.tokenizer/'tokenizer.json'))
    environment=jinja2.Environment(extensions=['jinja2.ext.loopcontrols'])
    environment.filters['tojson']=lambda value,ensure_ascii=False,**kwargs:json.dumps(value,ensure_ascii=ensure_ascii)
    def template_error(message):raise ValueError(message)
    environment.globals['raise_exception']=template_error
    template=environment.from_string((args.tokenizer/'chat_template.jinja').read_text())
    sys.path.insert(0,str(ROOT/'runtime/colibri/c'))
    from openai_server import render_chat_qwen
    clarify={'type':'function','function':{'name':'clarify','description':'Ask for missing details, clarify an ambiguous metric, or explain unsupported requests. Choose the current user message language; the backend writes the response.','parameters':CLARIFICATION_SCHEMA}}
    blocked=[]
    for directory in ('facturation','facturation-v2','facturation-v3-en-fr'):
        path=ROOT/'training/datasets'/directory/'test.eval.jsonl'
        if path.exists():blocked.extend(json.loads(line)['messages'][-1]['content']for line in path.read_text().splitlines())
    blocked_norm={normalized(text)for text in blocked}
    blocked_shapes={delexicalized(text)for text in blocked}
    seen={};shapes={'train':{},'valid':{}};outputs={'train':[],'valid':[]};evals={'train':[],'valid':[]};lengths=[];coverage=Counter();groups=set();errors=[]
    for scenario in SCENARIOS:
        split,key=scenario['split'],scenario['key']
        if key in groups:raise ValueError('Scenario group reused: '+key)
        groups.add(key)
        source_tools=[ChatAITool(x['function']['name'],x['function']['description'],x['function']['parameters'],{},None)for x in contracts['profiles'][scenario['profile']]]
        for language,text in zip(LANGS,scenario['texts']):
            history=[{'role':'user','content':pair[LANGS.index(language)]}for pair in scenario['history']]
            for item in [text]+[x['content']for x in history]:validate_text(item)
            context={'application':'facturation','today':'2027-11-18' if split=='train' else '2028-09-23','currency_default':'MAD','interface_language':language,'current_invoice_id':None,'previous_result_type':None,'previous_result_count':0,**scenario['context']}
            offered=shortlist(text,source_tools,context);schemas=[tool.schema()for tool in offered]
            expected_args=dict(scenario['arguments']);tool=scenario['tool']
            if tool=='clarify':expected_args['language']=language;schema=CLARIFICATION_SCHEMA
            else:
                match=next((t for t in offered if t.name==tool),None)
                if not match:errors.append(f'{split}/{key}/{language}: shortlist omitted {tool}');continue
                schema=match.input_schema
            if tool=='knowledge':expected_args={'query':text}
            Draft202012Validator(schema).validate(expected_args)
            validate_business_action(tool,expected_args,context,text)
            messages=[{'role':'system','content':SYSTEM+'\nTrusted context: '+json.dumps(context,ensure_ascii=False)},*history,{'role':'user','content':text}]
            signature=json.dumps(messages[1:],ensure_ascii=False,sort_keys=True)+'|'+scenario['profile']+'|'+json.dumps(scenario['context'],sort_keys=True)
            if signature in seen:raise ValueError(f'Duplicate user/context scenario: {seen[signature]} / {key}')
            seen[signature]=key
            shape=delexicalized(text)
            if split=='train' and (normalized(text) in blocked_norm or shape in blocked_shapes):raise ValueError('Historical held-out collision: '+key)
            for other,other_key in shapes['valid' if split=='train' else 'train'].items():
                if shape==other or (min(len(shape),len(other))>=45 and SequenceMatcher(None,shape,other).ratio()>=.94):raise ValueError(f'Cross-split near duplicate: {key}/{other_key}')
            shapes[split][shape]=key
            tools=schemas+[clarify]
            assistant={'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':tool,'arguments':expected_args}}]}
            full=render_template(template,messages+[assistant],tools,generation=False)
            prefix=render_template(template,messages,tools,generation=True)
            if not full.startswith(prefix):raise ValueError('Template assistant boundary mismatch: '+key)
            if prefix!=render_chat_qwen(messages,tools=tools,enable_thinking=False):raise ValueError('Colibri template mismatch: '+key)
            full_ids=tokenizer.encode(full,add_special_tokens=False).ids;prefix_ids=tokenizer.encode(prefix,add_special_tokens=False).ids
            shared=0
            for left,right in zip(full_ids,prefix_ids):
                if left!=right:break
                shared+=1
            if len(prefix_ids)-shared>8:raise ValueError('Unexpected BPE boundary: '+key)
            if len(full_ids)>args.max_context:raise ValueError('Example exceeds context: '+key)
            lengths.append(len(full_ids));coverage[(split,tool)]+=1
            outputs[split].append({'messages':messages+[assistant],'tools':tools})
            evals[split].append({'id':f'{split}-{key}-{language}','group':key,'category':scenario['category'],'language':language,'capability_profile':scenario['profile'],'messages':messages,'offered_tools':[x.name for x in offered],'offered_tool_schemas':schemas,'expected':{'tool':tool,'arguments':expected_args}})
    if errors:raise ValueError('\n'.join(errors))
    directory=ROOT/'training/datasets/facturation-v4-en-fr'
    files={}
    for split in ('train','valid'):
        files[split+'.jsonl']=''.join(json.dumps(row,ensure_ascii=False)+'\n'for row in outputs[split])
        files[split+'.eval.jsonl']=''.join(json.dumps(row,ensure_ascii=False)+'\n'for row in evals[split])
    files['tool-schemas.json']=json.dumps(contracts['profiles']['staff_edit'],ensure_ascii=False,indent=2)+'\n'
    files['capability-schemas.json']=json.dumps(contracts,ensure_ascii=False,indent=2)+'\n'
    files['coverage.json']=json.dumps({'rows':{s:len(outputs[s])for s in outputs},'scenarios':{s:sum(x['split']==s for x in SCENARIOS)for s in outputs},'tools':{s:{t:n for (part,t),n in coverage.items()if part==s}for s in outputs},'capability_profiles':{s:dict(Counter(x['capability_profile']for x in evals[s]))for s in outputs},'history_rows':{s:sum(len(x['messages'])>2 for x in evals[s])for s in outputs},'template_tokens':{'minimum':min(lengths),'maximum':max(lengths),'context_limit':args.max_context}},ensure_ascii=False,indent=2)+'\n'
    manifest={'version':'facturation-synthetic-v4-en-fr','languages':list(LANGS),'source':'Independently authored synthetic capability/argument combinations from current registered contracts; no database connection or private business records.',
        'split_policy':'Scenario families and their two language variants stay together. Training and validation have separate phrasings and unseen filter combinations. Normalized/context duplicates and cross-split delexicalized near duplicates are rejected. Historical held-out prompts are exclusion-only.',
        'test_status':'NO TEST SET. Independent held-out scenarios must be authored and frozen separately; validation is development data.',
        'permissions':'Profiles represent backend capability sets, not an alternative role hierarchy. Tool execution must still reauthorize. All database connections are forbidden during export.',
        'limitations':['Synthetic planner actions only; no business execution or generated RAG-answer evaluation.','Numeric hints are uncommon explicit user inputs and never authorization. Most discovery uses names/products and previous_results.','Production context exposes previous result type/count, not IDs. Natural selected-document edits still need result selection/action cards; no invented context keys.','Lifecycle/object permission checks remain backend responsibilities; mutation calls propose confirmation, never execute writes.','Evaluator must consume per-case offered_tool_schemas to preserve capability-narrowed validation.','No accuracy or training result is claimed.'],
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'backend_source_sha256':contracts['source_sha256'],
        'core_source_sha256':{p:hashlib.sha256((ROOT/'src/chat_ai_assistant'/p).read_bytes()).hexdigest()for p in ('orchestrator.py','routing.py','clarifications.py','contracts.py')},
        'tokenizer_sha256':{p:hashlib.sha256((args.tokenizer/p).read_bytes()).hexdigest()for p in ('tokenizer.json','chat_template.jinja','tokenizer_config.json')},
        'validation':{'schema':True,'business_argument_invariants':True,'credentials_and_internal_prompt_keys':True,'cross_split_duplicates':True,'historical_heldout_exclusion':True,'colibri_hf_template_parity':True,'assistant_loss_boundary':True,'context_limit':True,'database_access':'forbidden'},
        'files':[{'file':name,'sha256':hashlib.sha256(content.encode()).hexdigest(),'rows':len(outputs[name.split('.')[0]]) if name.endswith('.jsonl') else None}for name,content in files.items()]}
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    # Complete all validation before writing anything; never silently change a version.
    for name,content in files.items():
        target=directory/name
        if target.exists() and target.read_text()!=content:raise ValueError('Frozen v4 differs; use a new version: '+name)
    directory.mkdir(parents=True,exist_ok=True)
    for name,content in files.items():(directory/name).write_text(content)
    print(files['coverage.json']);print('manifest_sha256',hashlib.sha256(files['manifest.json'].encode()).hexdigest())


if __name__=='__main__':main()
