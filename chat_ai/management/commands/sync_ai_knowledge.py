import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from chat_ai.models import KnowledgeDocument
from chat_ai.security import SECRET


class Command(BaseCommand):
    help='Synchronize only reviewed facturation JSON documents; no repository or database scraping.'
    def handle(self,*args,**options):
        source=Path(settings.CHAT_AI_KNOWLEDGE_PATH)
        files=sorted(source.glob('*.json'))
        if not files:raise CommandError('No approved knowledge documents; refusing to delete the existing index.')
        documents=[]
        for path in files:
            raw=path.read_text();doc=json.loads(raw)
            if doc.get('application_id')!='facturation' or doc.get('approved') is not True or SECRET.search(raw):raise CommandError('Unapproved or sensitive document: '+path.name)
            if set(doc.get('required_capabilities',[]))-{'read','create','stock_read','user_admin'}:raise CommandError('Unknown capability')
            if len(doc.get('content',''))>6000 or len(doc.get('document_id',''))>80:raise CommandError('Document exceeds limits')
            doc['document_version']=hashlib.sha256(raw.encode()).hexdigest();documents.append(doc)
        if len({d['document_id'] for d in documents})!=len(documents):raise CommandError('Duplicate document identifier')
        changed=0
        with transaction.atomic():
            for d in documents:
                if KnowledgeDocument.objects.filter(document_id=d['document_id'],document_version=d['document_version']).exists():continue
                defaults={k:d[k] for k in ('application_id','document_version','title','content','keywords','category','required_capabilities')}
                KnowledgeDocument.objects.update_or_create(document_id=d['document_id'],defaults=defaults);changed+=1
            deleted,_=KnowledgeDocument.objects.filter(application_id='facturation',tenant_scope__isnull=True).exclude(document_id__in=[d['document_id'] for d in documents]).delete()
        self.stdout.write(f'Updated {changed}; removed {deleted}; approved {len(documents)}.')
