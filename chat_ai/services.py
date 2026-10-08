from datetime import timedelta
import threading
import uuid
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from chat_ai_assistant.contracts import ChatAIError
from chat_ai_assistant.provider import ChatAIModelService, ModelConfig
from chat_ai_assistant.orchestrator import ChatAIOrchestrator
from .models import Conversation, Message, InferenceLease, KnowledgeDocument
from .security import authorization_stamp, validate_text
from .tools import ChatAIToolExecutor, registry
from .labels import FIELD_LABELS, selected_action_text
from chat_ai_assistant.presentation import labelled_text
from .shortcuts import shortcut_action


def get_conversation(user_id, id):
    conv=Conversation.objects.filter(pk=id,user_id=user_id,expires_at__gt=timezone.now()).first()
    if conv is None:raise ChatAIError('NOT_FOUND')
    if conv.authorization_stamp!=authorization_stamp(user_id,conv.company_id):
        raise ChatAIError('CONTEXT_EXPIRED')
    return conv


def authorize_delivery(user_id, conversation_id, knowledge_sources=None, cards=()):
    conv = get_conversation(user_id, conversation_id)
    source_groups = [knowledge_sources] if knowledge_sources is not None else []
    # Replayed knowledge cards may come from a fresh retrieval, so guard their
    # sources as well as the original sources supporting persisted prose.
    for card in cards:
        if card.get('type') == 'knowledge' and card.get('documents'):
            source_groups.append([{'document_id': doc['document_id'], 'version': doc['version']}
                                  for doc in card['documents']])
    # Revalidate references immediately before delivery, including staff revocation
    # or a record moved into another company while inference was running.
    executor = ChatAIToolExecutor(user_id, conv.company_id, uuid.uuid4(), audit=False)
    for card in cards:
        if card.get('type') in ('record_list','invoice','client') and card.get('items'):
            resource=card.get('resource','invoice' if card['type']=='invoice' else 'client')
            ids=[item['id'] for item in card['items']]
            if len(executor.read_records(resource,ids)) != len(ids):
                raise ChatAIError('CONTEXT_EXPIRED')
        if card.get('type') == 'confirmation':
            from .confirmation_history import replay_confirmation
            if replay_confirmation(executor, {'confirmation_id': card['action_id']})['type'] != 'confirmation':
                raise ChatAIError('CONTEXT_EXPIRED')
        if card.get('type')=='navigation':
            target=card['target']
            executor.navigate(target['resource'],identifier=target.get('identifier'))
    if source_groups:
        from .knowledge import ChatAIKnowledgeService
        executor = ChatAIToolExecutor(user_id, conv.company_id, uuid.uuid4(), audit=False)
        caps = executor.capabilities()
        if any(not ChatAIKnowledgeService.sources_authorized(sources, conv.company_id, caps)
               for sources in source_groups):
            raise ChatAIError('CONTEXT_EXPIRED')
    return conv


def get_model():
    return ChatAIModelService(ModelConfig(settings.CHAT_AI_MODEL_URL,settings.CHAT_AI_MODEL_ID,
        settings.CHAT_AI_MODEL_KEY,settings.CHAT_AI_MODEL_TIMEOUT,settings.CHAT_AI_MODEL_MAX_TOKENS,mode='native'))


def replay(executor, action):
    if not action:return []
    if action.get('confirmation_id'):
        from .confirmation_history import replay_confirmation
        return [replay_confirmation(executor, action)]
    from .documents import DOCUMENTS
    from . import catalog, operations
    resource=action.get('resource')
    if resource in ('invoice','quote','client',*DOCUMENTS,*catalog.CATALOG,*operations.OPERATIONS):
        return [{'type':'record_list','resource':resource,'items':executor.read_records(resource,action.get('ids',[])[:10])}]
    if action.get('tool') in ('financial_summary','navigate','knowledge','list_payments','invoice_pdf'):
        return [executor.execute(action['tool'],action['arguments'])]
    return []


def knowledge_sources_authorized(executor, action):
    """Saved prose is usable only while every exact original source remains approved."""
    from .knowledge import ChatAIKnowledgeService
    return ChatAIKnowledgeService.sources_authorized(
        action.get('knowledge_sources'), executor.company_id, executor.capabilities())


def replay_message(executor, message):
    """Refresh cards and withhold generated knowledge prose with revoked/stale sources."""
    text = message.text
    if message.role=='assistant':
        try:text=labelled_text(text,executor.output_labels())
        except ChatAIError:text=''
    elif message.action.get('selected_resource'):
        operation=message.text.split(' · ',1)[0]
        operation={'Modifier':'edit','Supprimer':'delete'}.get(operation,operation)
        text=selected_action_text(operation,message.action['selected_resource'])
    knowledge_answer = message.role == 'assistant' and message.action.get('tool') == 'knowledge'
    try:
        cards = replay(executor, message.action)
        if knowledge_answer and not knowledge_sources_authorized(executor, message.action):
            text = ''
    except ChatAIError:
        cards = []
        if knowledge_answer:
            text = ''
    return {'id': str(message.pk), 'role': message.role, 'text': text, 'cards': cards}


def stored_action(result, language='fr'):
    cards=result.get('cards',[])
    if cards and cards[0].get('type') == 'confirmation':
        return {'confirmation_id': cards[0]['action_id'], 'language': 'en' if language == 'en' else 'fr'}
    if cards and cards[0].get('type')=='navigation':
        target=cards[0]['target'];args={'resource':target['resource']}
        if target.get('identifier'):args['identifier']=target['identifier']
        return {'tool':'navigate','arguments':args}
    if cards and cards[0].get('resource') in ('invoice','client','quote','proforma','credit_note','delivery_note','article','payment','user','stock_balance','stock_movement','stock_receipt','stock_inventory','logistics_order') or cards and cards[0].get('type')=='invoice':
        card=cards[0]
        return {'resource':card.get('resource','invoice'),'ids':[x['id'] for x in card.get('items',[])]}
    action=result.get('action',{})
    if action.get('tool') == 'knowledge':
        sources = [{'document_id': doc['document_id'], 'version': doc['version']}
                   for card in cards if card.get('type') == 'knowledge'
                   for doc in card.get('documents', [])]
        return {**action, 'knowledge_sources': sources}
    return {} if action.get('tool')=='prepare_change' else action


class ChatAIConversationService:
    def run(self,user_id,conversation_id,text,request_id,context,emit,cancel):
        close_old_connections()
        owner=uuid.uuid4();acquired=False
        try:
            conv=get_conversation(user_id,conversation_id)
            text=validate_text(text)
            complete=conv.messages.filter(request_id=request_id,role='assistant').first()
            if complete:
                executor=ChatAIToolExecutor(user_id,conv.company_id,request_id,audit=False)
                response = replay_message(executor, complete)
                authorize_delivery(user_id, conversation_id, cards=response['cards'])
                if complete.action.get('tool') == 'knowledge':
                    emit('_knowledge.sources', {'sources': complete.action.get('knowledge_sources', [])})
                return response
            InferenceLease.objects.get_or_create(name='model')
            acquired=bool(InferenceLease.objects.filter(name='model').filter(Q(owner__isnull=True)|Q(expires_at__lt=timezone.now())).update(owner=owner,expires_at=timezone.now()+timedelta(seconds=settings.CHAT_AI_MODEL_TIMEOUT*2+60)))
            if not acquired:raise ChatAIError('BUSY')
            if conv.messages.count()>=60:raise ChatAIError('CONTEXT_LIMIT')
            user_message,created=Message.objects.get_or_create(conversation=conv,request_id=request_id,role='user',defaults={'text':text})
            if not created and user_message.text!=text:raise ChatAIError('INVALID_ARGUMENTS')
            executor=ChatAIToolExecutor(user_id,conv.company_id,request_id,conv.references,context)
            # Only user utterances, not historic business output, enter planner context.
            history=list(conv.messages.filter(role='user').exclude(pk=user_message.pk).order_by('-created_at')[:4])
            trusted={'application':'facturation','today':timezone.localdate().isoformat(),
                     'currency_default':'MAD',
                     'interface_language':context.get('interface_language','fr'),
                     'current_invoice_id':context.get('invoice_id'),
                     'previous_result_type':conv.references.get('resource'),
                     'previous_result_count':len(conv.references.get('ids',[]))}
            if context.get('invoice_id'):executor.invoice(context['invoice_id'])
            forced=shortcut_action(text)
            result=ChatAIOrchestrator(None if forced else get_model(),registry(),executor).run(text,context=trusted,forced_action=forced,
                history=[{'role':'user','content':m.text} for m in reversed(history)],emit=emit,cancel=cancel)
            if cancel.is_set():raise ChatAIError('CANCELLED')
            # Recheck immediately before persistence/delivery for JSON and SSE alike.
            authorize_delivery(user_id,conversation_id,cards=result['cards'])
            for card in result['cards']:
                if card.get('type') == 'knowledge' and card.get('documents'):
                    executor.authorize_knowledge(card['documents'])
            assistant=Message.objects.create(conversation=conv,request_id=request_id,role='assistant',text=result['text'][:6000],action=stored_action(result, context.get('interface_language', 'fr')))
            conv.references=executor.state;conv.save(update_fields=['references','updated_at'])
            return {'id':str(assistant.pk),'role':'assistant','text':assistant.text,'cards':result['cards']}
        finally:
            if acquired:InferenceLease.objects.filter(name='model',owner=owner).update(owner=None,expires_at=None)
            close_old_connections()
