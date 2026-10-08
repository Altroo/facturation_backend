import hashlib
from dataclasses import dataclass
import re
from django.conf import settings
from account.models import Membership, CustomUser
from company.models import Company
from chat_ai_assistant.contracts import ChatAIError

SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:Bearer\s+)[A-Za-z0-9._-]{16,}|(?:password|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*\S+", re.I)


def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000 or '\x00' in text:
        raise ChatAIError('INVALID_ARGUMENTS')
    if SECRET.search(text):
        raise ChatAIError('SENSITIVE_INPUT')
    return text.strip()


def authorize(user_id, company_id):
    if not settings.CHAT_AI_ASSISTANT_ENABLED:
        raise ChatAIError('APPLICATION_UNAVAILABLE')
    if not CustomUser.objects.filter(pk=user_id, is_active=True).exists():
        raise ChatAIError('NOT_AUTHENTICATED')
    membership = Membership.objects.select_related('role', 'user').filter(user_id=user_id, company_id=company_id).first()
    if not membership:
        raise ChatAIError('PERMISSION_DENIED')
    # Same read policy as CompanyAccessMixin and dashboard.parse_date_filters.
    return membership


@dataclass(frozen=True)
class ChatAIContext:
    user: CustomUser
    company_id: int
    membership: Membership | None


def authorize_context(user_id, company_id):
    """Assistant entry context only; never substitutes for business authorization."""
    if not settings.CHAT_AI_ASSISTANT_ENABLED:
        raise ChatAIError('APPLICATION_UNAVAILABLE')
    if type(company_id) is not int or not 1 <= company_id <= 2147483647:
        raise ChatAIError('INVALID_ARGUMENTS')
    user = CustomUser.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise ChatAIError('NOT_AUTHENTICATED')
    membership = Membership.objects.select_related('role').filter(user=user, company_id=company_id).first()
    if membership is None and not user.is_superuser:
        raise ChatAIError('PERMISSION_DENIED')
    if not Company.objects.filter(pk=company_id).exists():
        raise ChatAIError('NOT_FOUND')
    if membership is not None:
        membership.user = user
    return ChatAIContext(user, company_id, membership)


def authorization_stamp(user_id, company_id):
    context = authorize_context(user_id, company_id)
    m, user = context.membership, context.user
    membership = (m.pk, m.role_id, m.role.name if m.role_id else '',
                  m.can_validate_factures, m.can_change_document_status) if m else None
    return hashlib.sha256(repr(('context-v2', user.pk, context.company_id, membership,
                                user.is_staff, user.is_superuser)).encode()).hexdigest()
