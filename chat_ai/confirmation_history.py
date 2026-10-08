"""Replay confirmations without creating proposals or retaining business snapshots."""
from uuid import UUID

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chat_ai_assistant.contracts import ChatAIError
from .models import AuditEvent, PendingAction
from .security import authorize_context


MESSAGES = {
    'fr': {
        'confirmed_update': 'Modification effectuée. Votre identité est enregistrée dans l’historique.',
        'confirmed_delete': 'Suppression effectuée. Votre identité est enregistrée dans l’historique.',
        'expired': 'Cette demande de confirmation a expiré. Faites une nouvelle demande pour continuer.',
        'stale': 'Le document a changé depuis cette demande. Faites une nouvelle demande avant de confirmer.',
        'unavailable': 'Cette action n’est plus disponible. Faites une nouvelle demande pour continuer.',
    },
    'en': {
        'confirmed_update': 'Change completed. Your identity is recorded in the history.',
        'confirmed_delete': 'Deletion completed. Your identity is recorded in the history.',
        'expired': 'This confirmation request has expired. Make a new request to continue.',
        'stale': 'The record has changed since this request. Make a new request before confirming.',
        'unavailable': 'This action is no longer available. Make a new request to continue.',
    },
}


def replay_confirmation(executor, stored):
    """Return a freshly authorized preview or a non-actionable, non-sensitive status."""
    from .actions import fingerprint, target, validated_update

    language = 'en' if stored.get('language') == 'en' else 'fr'

    def status(code):
        return {'type': 'confirmation_status', 'status': code,
                'message': MESSAGES[language][code]}

    # Also guard direct helper callers, independently of conversation access.
    authorize_context(executor.user_id, executor.company_id)
    try:
        action_id = UUID(str(stored.get('confirmation_id', '')))
    except (ValueError, TypeError, AttributeError):
        return status('unavailable')
    audit = AuditEvent.objects.filter(
        actor_id=executor.user_id, company_id=executor.company_id,
        application='facturation', correlation_id=action_id,
        tool__in=('confirmed_update', 'confirmed_delete'), outcome='allowed',
    ).first()
    if audit:
        # Confirmed audit rows outlive the short-lived PendingAction, including
        # when the deleted record itself no longer exists. Never replay its data.
        return status(audit.tool)
    action = PendingAction.objects.filter(
        pk=action_id, user_id=executor.user_id, company_id=executor.company_id,
    ).first()
    if action is None or action.expires_at <= timezone.now():
        return status('expired')
    if action.consumed_at:
        return status('unavailable')
    try:
        obj = target(executor.user_id, executor.company_id, action.resource,
                     action.record_id, action.operation)
        if fingerprint(obj) != action.fingerprint:
            return status('stale')
        if action.operation == 'update':
            _, canonical = validated_update(obj, action.changes)
            if canonical != action.changes:
                return status('stale')
    except (ChatAIError, ValidationError):
        return status('unavailable')
    return {
        'type': 'confirmation', 'action_id': str(action.pk),
        'resource': action.resource, 'operation': action.operation,
        'record_id': obj.pk,
        'label': obj.numero_facture if action.resource == 'invoice' else str(obj)[:200],
        'company_id': executor.company_id, 'changes': action.changes,
        'before': {key: str(getattr(obj, key)) if getattr(obj, key) is not None else None
                   for key in action.changes},
        'warning': ('Deletion may also remove related data under the existing application rules. '
                    'It cannot be undone here.' if language == 'en' else
                    'La suppression peut aussi supprimer les données liées selon les règles existantes. '
                    'Cette opération ne peut pas être annulée ici.') if action.operation == 'delete' else '',
        'expires_at': action.expires_at.isoformat(),
    }
