import asyncio
from datetime import timedelta
import json
import queue
import threading
import uuid
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import StreamingHttpResponse
from django.db.models import OuterRef, Subquery
from django.db.models.functions import Substr
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import Throttled
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from chat_ai_assistant.contracts import ChatAIError
from .labels import selected_action_text, FIELD_LABELS
from chat_ai_assistant.presentation import labelled_text
from account.models import Membership
from .models import Conversation, Feedback, Message
from .services import ChatAIConversationService, get_conversation, replay_message, authorize_delivery, stored_action
from .security import authorize, authorization_stamp, validate_text
from .tools import ChatAIToolExecutor


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self,data):
        if not isinstance(data,dict) or set(data)-set(self.fields):
            raise serializers.ValidationError({'error':'Unsupported fields.'})
        return super().to_internal_value(data)


class NewConversation(StrictSerializer):
    company_id=serializers.IntegerField(min_value=1)


class Context(StrictSerializer):
    interface_language=serializers.ChoiceField(choices=['fr','en'],required=False)
    invoice_id=serializers.IntegerField(min_value=1,required=False)


class NewMessage(StrictSerializer):
    text=serializers.CharField(max_length=4000,trim_whitespace=True)
    request_id=serializers.UUIDField()
    context=Context(default=dict)


class FeedbackInput(StrictSerializer):
    message_id=serializers.UUIDField()
    helpful=serializers.BooleanField()


class ChatReadThrottle(UserRateThrottle):
    scope = 'chat_ai_read'
    rate = '120/minute'


class ChatMutationThrottle(UserRateThrottle):
    scope = 'chat_ai_mutation'
    rate = '60/minute'


class ChatInferenceThrottle(UserRateThrottle):
    scope = 'chat_ai_inference'
    rate = '12/minute'


class ChatConfirmationThrottle(UserRateThrottle):
    scope = 'chat_ai_confirmation'
    rate = '20/minute'


class ChatView(APIView):
    permission_classes=(IsAuthenticated,)
    throttle_classes=(ChatMutationThrottle,)

    def get_throttles(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [ChatReadThrottle()]
        return super().get_throttles()

    def initial(self,request,*args,**kwargs):
        super().initial(request,*args,**kwargs)
        if not settings.CHAT_AI_ASSISTANT_ENABLED:raise ChatAIError('APPLICATION_UNAVAILABLE')

    def handle_exception(self,exc):
        if isinstance(exc,ChatAIError):
            code=exc.code
            status= {'NOT_FOUND':404,'NOT_AUTHENTICATED':401,'PERMISSION_DENIED':403,'APPLICATION_UNAVAILABLE':503,'BUSY':429,'CONTEXT_EXPIRED':409}.get(code,400)
            response=Response({'error':{'code':code}},status=status)
            response['Cache-Control']='no-store'
            return response
        response = super().handle_exception(exc)
        if isinstance(exc, Throttled) and exc.wait is not None:
            # The application's envelope rebuilds DRF responses without headers.
            response['Retry-After'] = str(exc.wait)
        return response

    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response['Cache-Control']='no-store, private'
        return response


class CapabilitiesView(ChatView):
    def get(self,request):
        from core.permissions import can_create, can_update, can_delete, can_print
        from .shortcut_catalog import shortcut_catalog
        language = request.query_params.get('language', 'fr')
        companies=[]
        for m in Membership.objects.filter(user=request.user,company__isnull=False).select_related('company','user').order_by('company_id'):
            # Resolve existing roles, never accept capabilities supplied by the browser.
            company={'id':m.company_id,'name':m.company.raison_sociale,
                'can_update':can_update(m.user,m.company_id),'can_delete':can_delete(m.user,m.company_id),
                'can_print':can_print(m.user,m.company_id),'can_create':can_create(m.user,m.company_id)}
            company['suggestions']=['Trouver une facture','Affiche les factures impayées','Chercher un client']
            if company['can_create']:company['suggestions'].append('Comment créer une facture ?')
            company['shortcuts'] = shortcut_catalog(ChatAIToolExecutor(request.user.pk, m.company_id, uuid.uuid4(), audit=False), language)
            companies.append(company)
        # Stock's native GET policy also permits a superuser without membership.
        # These contexts advertise stock reads only; business tools retain membership checks.
        if request.user.is_superuser:
            from company.models import Company
            known={company['id'] for company in companies}
            for company in Company.objects.exclude(pk__in=known).order_by('pk'):
                companies.append({'id':company.pk,'name':company.raison_sociale,
                    'can_update':False,'can_delete':False,'can_print':False,'can_create':False,
                    'can_read_business':False,'suggestions':['Consulter le stock','Rechercher un mouvement de stock'],
                    'shortcuts':shortcut_catalog(ChatAIToolExecutor(request.user.pk, company.pk, uuid.uuid4(), audit=False), language)})
        return Response({'application':'facturation','read_only':False,'companies':companies,
            'languages':['fr','en'],'model':settings.CHAT_AI_MODEL_ID})



class ConversationsView(ChatView):
    def get(self,request):
        serializer=NewConversation(data=request.query_params.dict());serializer.is_valid(raise_exception=True)
        company=serializer.validated_data['company_id'];stamp=authorization_stamp(request.user.pk,company)
        first_message = Message.objects.filter(conversation_id=OuterRef('pk'), role='user').order_by('created_at').values('text')[:1]
        items=Conversation.objects.filter(user=request.user,company_id=company,authorization_stamp=stamp,expires_at__gt=timezone.now()).annotate(title=Substr(Subquery(first_message), 1, 120)).order_by('-updated_at')[:30]
        def readable_title(text):
            try:
                return labelled_text(text or 'Nouvelle conversation', FIELD_LABELS, strict_unknown=False)
            except ChatAIError:
                return 'Conversation'
        return Response([{'id':str(c.pk),'created_at':c.created_at,'updated_at':c.updated_at,'title':readable_title(c.title)} for c in items])

    def post(self,request):
        serializer=NewConversation(data=request.data);serializer.is_valid(raise_exception=True)
        company=serializer.validated_data['company_id'];stamp=authorization_stamp(request.user.pk,company)
        if Conversation.objects.filter(user=request.user,expires_at__gt=timezone.now()).count()>=100:raise ChatAIError('CONTEXT_LIMIT')
        conv=Conversation.objects.create(user=request.user,company_id=company,authorization_stamp=stamp,expires_at=timezone.now()+timedelta(days=settings.CHAT_AI_RETENTION_DAYS))
        return Response({'id':str(conv.pk),'company_id':company},status=201)


class ConversationView(ChatView):
    def get(self,request,id):
        conv=get_conversation(request.user.pk,id);messages=[]
        for m in conv.messages.all()[:60]:
            executor=ChatAIToolExecutor(request.user.pk,conv.company_id,uuid.uuid4(),audit=False)
            payload = replay_message(executor, m)
            messages.append({**payload, 'created_at': m.created_at})
        authorize_delivery(request.user.pk,id,cards=[card for message in messages for card in message['cards']])
        return Response({'id':str(conv.pk),'company_id':conv.company_id,'messages':messages,'results_refreshed':True})

    def delete(self,request,id):
        conv=get_conversation(request.user.pk,id);conv.delete()
        return Response(status=204)


class ChatAIEventStreamRenderer(JSONRenderer):
    # DRF negotiates Accept before post(); successful responses use the async stream.
    media_type = "text/event-stream"
    format = "event-stream"


class MessagesView(ChatView):
    throttle_classes = (ChatInferenceThrottle,)
    renderer_classes = (JSONRenderer, ChatAIEventStreamRenderer)
    def post(self,request,id):
        serializer=NewMessage(data=request.data);serializer.is_valid(raise_exception=True)
        data=serializer.validated_data;get_conversation(request.user.pk,id);validate_text(data['text'])
        user_id=request.user.pk
        cancel=threading.Event()
        if request.headers.get('Accept')!='text/event-stream':
            result=ChatAIConversationService().run(user_id,id,data['text'],data['request_id'],data['context'],lambda *_:None,cancel)
            return Response(result)

        async def events():
            output=queue.Queue(maxsize=256)
            knowledge_sources = None
            def emit(event,payload):
                nonlocal knowledge_sources
                if event == '_knowledge.sources':
                    knowledge_sources = payload['sources']
                    return
                if cancel.is_set():raise ChatAIError('CANCELLED')
                try:output.put_nowait((event,payload))
                except queue.Full:raise ChatAIError('CANCELLED')
            def work():
                try:
                    result=ChatAIConversationService().run(user_id,id,data['text'],data['request_id'],data['context'],emit,cancel)
                    emit('message.completed',result)
                except ChatAIError as exc:
                    if not cancel.is_set():output.put(('error',{'code':exc.code}))
                except Exception:
                    if not cancel.is_set():output.put(('error',{'code':'INTERNAL_ERROR'}))
            worker=asyncio.create_task(asyncio.to_thread(work))
            try:
                yield 'event: message.started\ndata: '+json.dumps({'request_id':str(data['request_id'])})+'\n\n'
                while True:
                    try:event,payload=output.get_nowait()
                    except queue.Empty:
                        if worker.done():break
                        await asyncio.sleep(.05)
                        continue
                    # JWT may expire while inference is running; do not send more private output.
                    expiry=request.auth.get('exp') if request.auth else None
                    if expiry and timezone.now().timestamp()>=expiry:
                        yield 'event: error\ndata: {"code":"NOT_AUTHENTICATED"}\n\n';break
                    try:await sync_to_async(authorize_delivery)(user_id,id,knowledge_sources,payload.get('cards',[]) if event == 'message.completed' else ())
                    except ChatAIError as exc:
                        yield 'event: error\ndata: '+json.dumps({'code':exc.code})+'\n\n';break
                    yield 'event: '+event+'\ndata: '+json.dumps(payload,ensure_ascii=False)+'\n\n'
                    if event in ('message.completed','error'):break
            finally:
                cancel.set()
                # The bounded worker releases its DB lease when upstream exits/timeout fires.
                worker.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        response=StreamingHttpResponse(events(),content_type='text/event-stream; charset=utf-8')
        response['X-Accel-Buffering']='no'
        return response


class FeedbackView(ChatView):
    def post(self,request):
        serializer=FeedbackInput(data=request.data);serializer.is_valid(raise_exception=True)
        data=serializer.validated_data
        message=Message.objects.filter(pk=data['message_id'],role='assistant',conversation__user=request.user).first()
        if not message:raise ChatAIError('NOT_FOUND')
        get_conversation(request.user.pk,message.conversation_id)
        Feedback.objects.update_or_create(message=message,user=request.user,defaults={'helpful':data['helpful']})
        return Response({'saved':True})


class ConfirmationInput(StrictSerializer):
    confirmed=serializers.BooleanField()


class ConfirmActionView(ChatView):
    throttle_classes = (ChatConfirmationThrottle,)

    def post(self,request,id):
        serializer=ConfirmationInput(data=request.data);serializer.is_valid(raise_exception=True)
        if serializer.validated_data['confirmed'] is not True:raise ChatAIError('INVALID_ARGUMENTS')
        from .actions import confirm
        return Response(confirm(request,id))


class RecordSelection(StrictSerializer):
    resource=serializers.ChoiceField(choices=['invoice','quote','client','proforma','credit_note','delivery_note'])
    identifier=serializers.IntegerField(min_value=1)
    operation=serializers.ChoiceField(choices=['edit','delete'])


class RecordSelectionView(ChatView):
    def post(self,request,id):
        conv=get_conversation(request.user.pk,id)
        serializer=RecordSelection(data=request.data);serializer.is_valid(raise_exception=True)
        data=serializer.validated_data
        state=conv.references
        if state.get('resource')!=data['resource'] or data['identifier'] not in state.get('ids',[]) or state.get('expires_at','')<timezone.now().isoformat():raise ChatAIError('CONTEXT_EXPIRED')
        request_id=uuid.uuid4()
        executor=ChatAIToolExecutor(request.user.pk,conv.company_id,request_id)
        if data['operation']=='delete':card=executor.execute('prepare_change',{'resource':data['resource'],'identifier':data['identifier'],'operation':'delete'})
        else:card=executor.execute('navigate',{'resource':data['resource']+'_edit','identifier':data['identifier']})
        authorize_delivery(request.user.pk,id,cards=[card])
        Message.objects.create(conversation=conv,role='user',request_id=request_id,text=selected_action_text(data['operation'],data['resource']),action={'selected_resource':data['resource'],'selected_identifier':data['identifier']})
        message=Message.objects.create(conversation=conv,role='assistant',request_id=request_id,text='',action=stored_action({'cards':[card]}))
        return Response({'id':str(message.pk),'role':'assistant','text':'','cards':[card]})
