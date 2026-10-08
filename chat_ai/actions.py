"""Writes require a user-bound preview and a separate explicit confirmation request."""
from datetime import timedelta
import hashlib
import json
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from core.permissions import can_delete, can_update
from facture_client.models import FactureClient
from facture_client.serializers import FactureClientDetailSerializer
from client.models import Client
from devi.models import Devi
from devi.serializers import DeviDetailSerializer
from client.serializers import ClientDetailSerializer
from chat_ai_assistant.contracts import ChatAIError
from .models import PendingAction, AuditEvent
from .documents import DOCUMENTS, scoped_queryset
from .security import authorize, validate_text

FIELDS={**{name:set(adapter.editable_fields) for name,adapter in DOCUMENTS.items()},'quote':{'remarque','date_echeance'},'invoice':{'remarque','termes_paiement','date_echeance'},'client':{'raison_sociale','nom','prenom','adresse'}}


def target(user_id,company_id,resource,id,operation,lock=False):
    member=authorize(user_id,company_id)
    allowed=can_delete(member.user,company_id) if operation=='delete' else can_update(member.user,company_id)
    if not allowed:raise ChatAIError('PERMISSION_DENIED')
    model=DOCUMENTS[resource].model if resource in DOCUMENTS else {'invoice':FactureClient,'quote':Devi,'client':Client}.get(resource)
    if model is None:raise ChatAIError('INVALID_ARGUMENTS')
    qs=scoped_queryset(company_id,resource) if resource in DOCUMENTS else model.objects.filter(company_id=company_id)
    if resource in ('invoice','quote'):qs=qs.filter(client__company_id=company_id)
    if lock:qs=qs.select_for_update(of=('self',))
    obj=qs.filter(pk=id).first()
    if not obj:raise ChatAIError('NOT_FOUND')
    return obj


def serializer_class(obj):
    for adapter in DOCUMENTS.values():
        if isinstance(obj,adapter.model):return adapter.serializer_class
    if isinstance(obj,FactureClient):return FactureClientDetailSerializer
    if isinstance(obj,Devi):return DeviDetailSerializer
    return ClientDetailSerializer


def update_payload(obj, changes):
    data=dict(changes)
    adapter=DOCUMENTS.get('credit_note')
    if adapter and isinstance(obj,adapter.model):
        # The existing partial validator needs the current client. Do not pass
        # origin/payment fields: that branch can reset existing credit terms.
        data['client']=obj.client_id
        if obj.facture_origine_id and not obj.mode_paiement_id and obj.facture_origine.mode_paiement_id:
            # Its model.save would also change a payment field outside this
            # bounded preview. Use the existing edit form for that legacy case.
            raise ChatAIError('ACTION_REJECTED')
    return data


def validated_update(obj, changes, request=None):
    """Preview only what the native serializer will really change.

    Field-level normalization (for example whitespace and ISO dates) is shown
    canonically. Business rules that discard an input or modify an unrequested
    field must use the existing form, never a misleading assistant preview.
    """
    serializer=serializer_class(obj)(obj,data=update_payload(obj,changes),partial=True,
        context={'request':request} if request is not None else {})
    serializer.is_valid(raise_exception=True)
    canonical={}
    for key,value in changes.items():
        field=serializer.fields.get(key)
        if field is None or field.read_only or key not in serializer.validated_data:
            raise ChatAIError('ACTION_REJECTED')
        validated=serializer.validated_data[key]
        if field.run_validation(value)!=validated:
            raise ChatAIError('ACTION_REJECTED')
        if getattr(obj,key)!=validated:
            canonical[key]=None if validated is None else field.to_representation(validated)
    for key,value in serializer.validated_data.items():
        if key not in changes and (not hasattr(obj,key) or getattr(obj,key)!=value):
            raise ChatAIError('ACTION_REJECTED')
    if not canonical:raise ChatAIError('ACTION_REJECTED')
    return serializer,canonical


def fingerprint(obj):
    # Changes to related payments/lines/credit totals also invalidate an invoice preview.
    serializer=serializer_class(obj)
    return hashlib.sha256(json.dumps(serializer(obj).data,sort_keys=True,default=str).encode()).hexdigest()


def prepare(executor,resource,identifier,operation,changes=None):
    if resource not in FIELDS or operation not in ('update','delete'):raise ChatAIError('INVALID_ARGUMENTS')
    changes=changes or {}
    if operation=='update' and (not changes or set(changes)-FIELDS[resource]):raise ChatAIError('INVALID_ARGUMENTS')
    if operation=='delete' and changes:raise ChatAIError('INVALID_ARGUMENTS')
    for value in changes.values():
        if value is not None and value!='':validate_text(value)
    obj=target(executor.user_id,executor.company_id,resource,identifier,operation)
    if operation=='update':
        try:_,changes=validated_update(obj,changes)
        except ValidationError as exc:raise ChatAIError('INVALID_ARGUMENTS') from exc
    action=PendingAction.objects.create(instruction_id=executor.correlation_id,user_id=executor.user_id,company_id=executor.company_id,resource=resource,record_id=obj.pk,operation=operation,changes=changes,fingerprint=fingerprint(obj),expires_at=timezone.now()+timedelta(minutes=5))
    return {'type':'confirmation','action_id':str(action.pk),'resource':resource,'operation':operation,
        'record_id':obj.pk,'label':obj.numero_facture if resource=='invoice' else str(obj)[:200],
        'company_id':executor.company_id,'changes':changes,'before':{key:str(getattr(obj,key)) if getattr(obj,key) is not None else None for key in changes},
        'warning':'La suppression peut aussi supprimer les données liées selon les règles existantes. Cette opération ne peut pas être annulée ici.' if operation=='delete' else '',
        'expires_at':action.expires_at.isoformat()}


def confirm(request,action_id):
    with transaction.atomic():
        action=PendingAction.objects.select_for_update().filter(pk=action_id,user=request.user).first()
        if not action:raise ChatAIError('NOT_FOUND')
        if action.consumed_at or action.expires_at<=timezone.now():raise ChatAIError('CONTEXT_EXPIRED')
        obj=target(request.user.pk,action.company_id,action.resource,action.record_id,action.operation,lock=True)
        if fingerprint(obj)!=action.fingerprint:raise ChatAIError('STALE_ACTION')
        obj._history_user = request.user
        obj._change_reason = 'Chat AI Assistant confirmation ' + str(action.pk)
        try:
            if action.operation=='delete':
                if action.resource=='delivery_note':
                    from stock.services import delete_delivery_with_stock
                    delete_delivery_with_stock(obj, request.user)
                else:
                    obj.delete()
            else:
                serializer,canonical=validated_update(obj,action.changes,request)
                if canonical!=action.changes:raise ChatAIError('ACTION_REJECTED')
                serializer.save()
        except (ProtectedError,ValidationError) as exc:raise ChatAIError('ACTION_REJECTED') from exc
        action.consumed_at=timezone.now();action.save(update_fields=['consumed_at'])
        AuditEvent.objects.create(user=request.user,actor_id=request.user.pk,actor_label=str(request.user)[:254],
            company_id=action.company_id,resource=action.resource,record_id=action.record_id,
            changed_fields=sorted(action.changes),tool='confirmed_'+action.operation,
            outcome='allowed',instruction_id=action.instruction_id,correlation_id=action.pk,model_version='trusted-application-action')
    return {'success':True,'operation':action.operation,'resource':action.resource,'record_id':action.record_id}
