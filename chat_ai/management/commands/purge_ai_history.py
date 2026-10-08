from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from chat_ai.models import Conversation, AuditEvent, PendingAction

class Command(BaseCommand):
    help='Delete expired conversations/feedback and audit records older than configured retention.'
    def handle(self,*args,**kwargs):
        PendingAction.objects.filter(expires_at__lte=timezone.now()).delete()
        count,_=Conversation.objects.filter(expires_at__lte=timezone.now()).delete()
        audits,_=AuditEvent.objects.exclude(tool__startswith='confirmed_').filter(created_at__lt=timezone.now()-timedelta(days=settings.CHAT_AI_RETENTION_DAYS)).delete()
        self.stdout.write(f'Deleted {count} expired history rows and {audits} audits.')
