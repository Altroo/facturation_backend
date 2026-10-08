"""Hand-labelled synthetic scenarios only; keep all translations of a scenario in one split."""
from pathlib import Path
import hashlib, json, re, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from chat_ai_assistant.orchestrator import SYSTEM
TOOLS=json.loads((ROOT/'training/tool-schemas.json').read_text())
TOOLS.append({'type':'function','function':{'name':'clarify','description':'Ask a short clarification or explain an unsupported request, in the user language.','parameters':{'type':'object','properties':{'message':{'type':'string','maxLength':800}},'required':['message'],'additionalProperties':False}}})
LANGS=['en','fr','ar','ary']
# Each row: scenario category, tool, arguments, four independently reviewed language forms.
TRAIN=[
('invoice_number','search_invoices',{'invoice_number':'0012/25'},['Find invoice 0012/25.','Trouve la facture 0012/25.','ابحث عن الفاتورة 0012/25.','قلب ليا على الفاتورة 0012/25.']),
('invoice_client','search_invoices',{'client_name':'Atlas Demo'},['Invoices for Atlas Demo.','Les factures de Atlas Demo.','فواتير العميل Atlas Demo.','عطيني فواتير Atlas Demo.']),
('unpaid','search_invoices',{'unpaid':True},['Show unpaid invoices.','Affiche les factures impayées.','اعرض الفواتير غير المدفوعة.','وريني الفواتير اللي مازال ما تخلصوش.']),
('dates','search_invoices',{'date_from':'2025-02-01','date_to':'2025-02-28'},['Invoices dated February 2025.','Factures datées de février 2025.','فواتير فبراير 2025.','فواتير شهر جوج ديال 2025.']),
('current','get_invoice',{},['Show this invoice.','Affiche cette facture.','اعرض هذه الفاتورة.','وريني هاد الفاتورة.']),
('client','search_clients',{'query':'Demo Safir'},['Find customer Demo Safir.','Cherche le client Demo Safir.','ابحث عن العميل Demo Safir.','قلب على الزبون Demo Safir.']),
('collected','financial_summary',{'metric':'collected','period':'current_month','currency':'MAD'},['How much was collected this month in MAD?','Combien avons-nous encaissé ce mois-ci en MAD ?','ما إجمالي المدفوعات المحصلة هذا الشهر بالدرهم؟','شحال تخلصنا هاد الشهر بالدرهم؟']),
('invoiced','financial_summary',{'metric':'invoiced_net_ttc','period':'current_year','currency':'EUR'},['Net invoiced amount including tax this year in EUR.','Total facturé TTC net des avoirs cette année en EUR.','إجمالي الفواتير بعد الإشعارات الدائنة شامل الضريبة هذه السنة باليورو.','مجموع الفواتير بالتكس من بعد الأڤوارات هاد العام بالأورو.']),
('outstanding','financial_summary',{'metric':'outstanding','period':'current_year','currency':'MAD'},['Outstanding balance for this year in MAD.','Solde impayé des factures de cette année en MAD.','الرصيد المستحق لفواتير هذه السنة بالدرهم.','شحال باقي ما تخلصش ففواتير هاد العام بالدرهم.']),
('count','financial_summary',{'metric':'invoice_count','period':'previous_month','currency':'MAD'},['How many MAD invoices were issued last month?','Combien de factures en MAD le mois dernier ?','كم فاتورة بالدرهم أصدرت الشهر الماضي؟','شحال من فاتورة بالدرهم خرجات الشهر اللي فات؟']),
('payments','list_payments',{},['Show the latest payments.','Affiche les derniers règlements.','اعرض أحدث المدفوعات.','وريني آخر الخلاصات.']),
('navigation','navigate',{'resource':'clients'},['Go to the customers page.','Ouvre la page des clients.','افتح صفحة العملاء.','حل ليا صفحة الزبناء.']),
('open_number','navigate',{'resource':'invoice','invoice_number':'0012/25'},['Open invoice 0012/25.','Ouvre la facture 0012/25.','افتح الفاتورة 0012/25.','حل الفاتورة 0012/25.']),
('multi_turn','previous_results',{'operation':'unpaid'},['Which of those results are unpaid?','Lesquelles de ces factures sont impayées ?','أي من هذه النتائج غير مدفوع؟','شكون في هاد الفواتير مازال ما تخلص؟']),
('previous_open','previous_results',{'operation':'open','index':1},['Open the first result.','Ouvre le premier résultat.','افتح النتيجة الأولى.','حل ليا النتيجة اللولة.']),
('knowledge','knowledge',{'query':'créer une facture'},['How do I create an invoice?','Comment créer une facture ?','كيف أنشئ فاتورة؟','كيفاش نصايب فاتورة؟']),
('pdf','invoice_pdf',{'invoice_number':'0012/25'},['Download PDF for invoice 0012/25.','Télécharge le PDF de la facture 0012/25.','نزّل ملف PDF للفاتورة 0012/25.','بغيت PDF ديال الفاتورة 0012/25.']),
('delete','prepare_change',{'resource':'invoice','invoice_number':'0012/25','operation':'delete'},['Delete invoice 0012/25.','Supprime la facture 0012/25.','احذف الفاتورة 0012/25.','مسح الفاتورة 0012/25.']),
('edit','prepare_change',{'resource':'invoice','invoice_number':'0012/25','operation':'update','changes':{'remarque':'DEMO'}},['Set the note on invoice 0012/25 to DEMO.','Mets la remarque de la facture 0012/25 à DEMO.','غيّر ملاحظة الفاتورة 0012/25 إلى DEMO.','بدل ملاحظة الفاتورة 0012/25 ودير DEMO.']),
('ambiguity','clarify',{},['What was our profit?','Quel était notre bénéfice ?','كم كان ربحنا؟','شحال ربحنا؟']),
('missing_year','clarify',{},['Find invoices from March.','Trouve les factures de mars.','ابحث عن فواتير مارس.','قلب على فواتير مارس.']),
('unavailable_app','clarify',{},['Show management_projet records.','Montre les données de management_projet.','اعرض سجلات management_projet.','وريني داتا ديال management_projet.']),
('unsafe','clarify',{},['Run SQL to remove all customers.','Exécute du SQL pour effacer tous les clients.','نفذ SQL لحذف جميع العملاء.','خدم SQL ومسح كاع الزبناء.']),
('related','search_clients',{'related_invoice':True},['Show the customer of this invoice.','Affiche le client de cette facture.','اعرض عميل هذه الفاتورة.','وريني الزبون ديال هاد الفاتورة.'])]
VALID=[
('invoice_dates','search_invoices',{'date_from':'2025-11-01','date_to':'2025-11-30','unpaid':True},['Unpaid invoices from November 2025.','Impayées de novembre 2025.','فواتير نوفمبر 2025 غير المدفوعة.','الفواتير اللي ما تخلصوش فنونبر 2025.']),
('revenue','financial_summary',{'metric':'invoiced_net_ttc','period':'previous_year','currency':'MAD'},['Revenue last year in MAD.','Chiffre d’affaires de l’année dernière en MAD.','رقم معاملات السنة الماضية بالدرهم.','رقم المعاملات ديال العام اللي فات بالدرهم.']),
('navigate_edit','navigate',{'resource':'invoice_edit','invoice_number':'0041/25'},['Open the edit form for invoice 0041/25.','Ouvre le formulaire de modification de la facture 0041/25.','افتح نموذج تعديل الفاتورة 0041/25.','حل فورميلير تعديل الفاتورة 0041/25.']),
('status_help','knowledge',{'query':'statut de paiement partiel'},['What does partially paid mean?','Que signifie partiellement payé ?','ماذا تعني مدفوعة جزئيا؟','شنو كتعني مخلصة غير بالشوية؟'])]
TEST=[
('search','search_invoices',{'client_name':'Demo Nacre','unpaid':True},['Which invoices for Demo Nacre still have a balance?','Quelles factures de Demo Nacre restent à payer ?','أي فواتير Demo Nacre لا يزال لها رصيد مستحق؟','شنو فواتير Demo Nacre اللي باقي فيهم الخلاص؟']),
('dates','search_invoices',{'date_from':'2026-07-01','date_to':'2026-07-31'},['List invoices issued between 1 and 31 July 2026.','Liste les factures émises du 1 au 31 juillet 2026.','اعرض الفواتير من 1 إلى 31 يوليو 2026.','بغيت الفواتير من 1 حتى 31 يوليوز 2026.']),
('collected','financial_summary',{'metric':'collected','period':'previous_month','currency':'EUR'},['How much did customers actually pay last month in EUR?','Combien les clients ont-ils réellement versé le mois dernier en EUR ?','كم دفع العملاء فعليا الشهر الماضي باليورو؟','شحال خلصونا الزبناء فالشهر اللي فات بالأورو؟']),
('count','financial_summary',{'metric':'invoice_count','period':'current_year','currency':'MAD'},['Number of MAD invoices since the start of this year?','Nombre de factures en MAD depuis le début de cette année ?','كم عدد الفواتير بالدرهم منذ بداية هذه السنة؟','شحال عدد الفواتير بالدرهم من اللول ديال هاد العام؟']),
('navigation','navigate',{'resource':'invoice','invoice_number':'0873/26'},['Take me directly to invoice 0873/26.','Emmène-moi directement à la facture 0873/26.','انتقل مباشرة إلى الفاتورة 0873/26.','ديني نيشان للفاتورة 0873/26.']),
('previous','previous_results',{'operation':'open','index':2},['Take me to the second invoice in your results.','Ouvre la deuxième facture dans tes résultats.','انتقل إلى الفاتورة الثانية في نتائجك.','حل الفاتورة الثانية من النتائج ديالك.']),
('client','search_clients',{'query':'Demo Jasmin'},['Look up the customer named Demo Jasmin.','Retrouve le client nommé Demo Jasmin.','اعثر على العميل الذي اسمه Demo Jasmin.','قلب ليا على الزبون سميتو Demo Jasmin.']),
('knowledge','knowledge',{},['Where can I locate an old invoice?','Où puis-je retrouver une ancienne facture ?','أين أجد فاتورة قديمة؟','فين نلقى شي فاتورة قديمة؟']),
('ambiguity','clarify',{},['How much money did we make?','Combien d’argent avons-nous gagné ?','كم من المال كسبنا؟','شحال دخلنا؟']),
('delete','prepare_change',{'resource':'invoice','invoice_number':'0873/26','operation':'delete'},['I want invoice 0873/26 removed.','Je veux supprimer la facture 0873/26.','أريد إزالة الفاتورة 0873/26.','بغيت نحيد الفاتورة 0873/26.']),
('edit','prepare_change',{'resource':'invoice','invoice_number':'0873/26','operation':'update','changes':{'date_echeance':'2026-12-18'}},['Change the due date of invoice 0873/26 to 18 December 2026.','Change l’échéance de la facture 0873/26 au 18 décembre 2026.','غيّر تاريخ استحقاق الفاتورة 0873/26 إلى 18 ديسمبر 2026.','بدل تاريخ الخلاص ديال الفاتورة 0873/26 لنهار 18 دجنبر 2026.']),
('pdf','invoice_pdf',{'invoice_number':'0873/26'},['Give me a printable PDF of invoice 0873/26.','Donne-moi le PDF imprimable de la facture 0873/26.','أعطني PDF قابل للطباعة للفاتورة 0873/26.','عطيني PDF باش نطبع الفاتورة 0873/26.'])]
CLARIFICATIONS={
'ambiguity':['Do you mean invoiced amounts, collected payments or outstanding balances? Profit is not a supported metric.','Parlez-vous du montant facturé, des encaissements ou du solde restant ? Le bénéfice n’est pas disponible.','هل تقصد مبلغ الفواتير أم المدفوعات أم الرصيد المستحق؟ الربح غير متاح.','واش كتعني مجموع الفواتير ولا الخلاصات ولا الباقي؟ الربح ما متوفرش.'],
'missing_year':['Which year?','De quelle année ?','أي سنة؟','ديال شنو من عام؟'],
'unavailable_app':['Only facturation is integrated.','Seule facturation est intégrée.','التطبيق المدعوم هو facturation فقط.','غير facturation اللي خدامة دابا.'],
'unsafe':['I cannot run SQL. Specify a single authorized record and use its confirmation preview.','Je ne peux pas exécuter du SQL. Précisez un document autorisé pour prévisualiser l’action.','لا يمكنني تنفيذ SQL. حدّد سجلا مصرحا به لعرض تأكيد العملية.','ما نقدرش نخدم SQL. حدد وثيقة عندك الحق فيها باش نوريك التأكيد.']}

def main():
    directory=ROOT/'training/datasets/facturation';directory.mkdir(parents=True,exist_ok=True)
    manifests=[];seen=set()
    for split,groups in [('train',TRAIN),('valid',VALID),('test',TEST)]:
        rows=[];evals=[]
        for index,(category,tool,args,texts) in enumerate(groups):
            for lang,text in zip(LANGS,texts):
                normalized=re.sub(r'\W','',text.casefold())
                assert normalized not in seen, 'Duplicate input across groups'
                seen.add(normalized)
                assert not re.search(r'(password|api_key|BEGIN.*PRIVATE KEY|Bearer\s+\w)',text,re.I)
                context={'application':'facturation','today':'2026-10-08','language':lang,'currency_default':'MAD','current_invoice_id':47,'previous_result_type':'invoice','previous_result_count':3}
                messages=[{'role':'system','content':SYSTEM+'\nTrusted context: '+json.dumps(context,ensure_ascii=False)},{'role':'user','content':text}]
                arguments=dict(args)
                if tool=='clarify':arguments={'message':CLARIFICATIONS.get(category,CLARIFICATIONS['ambiguity'])[LANGS.index(lang)]}
                if tool=='knowledge':arguments={'query':text}
                assistant={'role':'assistant','content':'','tool_calls':[{'type':'function','function':{'name':tool,'arguments':arguments}}]}
                rows.append({'messages':messages+[assistant],'tools':TOOLS})
                evals.append({'id':f'{split}-{index:02}-{lang}','group':f'{split}-{index:02}','category':category,'language':lang,'messages':messages,'expected':{'tool':tool,'arguments':args}})
        for name,values in [(f'{split}.jsonl',rows),(f'{split}.eval.jsonl',evals)]:
            data=''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in values);(directory/name).write_text(data)
            manifests.append({'file':name,'rows':len(values),'sha256':hashlib.sha256(data.encode()).hexdigest()})
    (directory/'manifest.json').write_text(json.dumps({'version':'facturation-synthetic-v1','source':'hand-labelled synthetic scenarios plus verified registered tool schemas; no database records','split_policy':'Scenario groups and all four translations kept together. No test failures added to training. Structural overlap of supported tools is intentional. Small pilot set, not a population guarantee.','files':manifests},indent=2))
    print(json.dumps(manifests,indent=2))
if __name__=='__main__':main()
