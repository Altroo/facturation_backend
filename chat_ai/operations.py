"""Fixed read adapters for existing stock and logistics operations.

No bootstrap, alert, synchronization, mutation, or write serializer is invoked.
Call search/detail through the audited executor; company IDs come from its context.
"""
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
import re

from django.conf import settings
from django.db.models import Exists, F, OuterRef, Q
from account.models import CustomUser, Membership
from company.models import Company
from logistique.models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma
from stock.models import StockBalance, StockMovement, StockReceipt, StockReceiptLine, InventorySession, InventoryLine
from stock.services import INCOMING_EXCLUDED_STATUSES, prepare_balance_snapshots
from chat_ai_assistant.contracts import ChatAIError


@dataclass(frozen=True)
class OperationAdapter:
    model: type
    route: str
    date_field: str
    filters: frozenset[str]
    statuses: frozenset[str]


OPERATIONS = MappingProxyType({
    'stock_balance': OperationAdapter(StockBalance, '/dashboard/stock/', 'date_updated',
        frozenset({'reference', 'product_name', 'location_name'}),
        frozenset({'a_approvisionner', 'minimum', 'disponible'})),
    'stock_movement': OperationAdapter(StockMovement, '/dashboard/stock/movements/', 'date_created',
        frozenset({'reference', 'product_name', 'location_name'}),
        frozenset(value for value, _ in StockMovement.TYPE_CHOICES)),
    'stock_receipt': OperationAdapter(StockReceipt, '/dashboard/stock/receipts/', 'date_created',
        frozenset({'reference', 'product_name', 'location_name', 'client_name', 'supplier_name'}),
        frozenset(value for value, _ in StockReceipt.STATUS_CHOICES)),
    'stock_inventory': OperationAdapter(InventorySession, '/dashboard/stock/inventories/', 'date_created',
        frozenset({'reference', 'product_name', 'location_name'}),
        frozenset(value for value, _ in InventorySession.STATUS_CHOICES)),
    'logistics_order': OperationAdapter(LogisticsOrder, '/dashboard/logistique/', 'date_created',
        frozenset({'reference', 'product_name', 'location_name', 'client_name', 'supplier_name'}),
        frozenset(value for value, _ in LogisticsOrder.STATUT_CHOICES)),
})


def _adapter(resource):
    if not isinstance(resource, str) or resource not in OPERATIONS:
        raise ChatAIError('INVALID_ARGUMENTS')
    return OPERATIONS[resource]


def _identifier(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise ChatAIError('INVALID_ARGUMENTS')
    return value


def authorize(executor, resource):
    """Mirror stock GET's superuser/member policy and logistics member policy."""
    _adapter(resource)
    company_id = _identifier(executor.company_id)
    if not settings.CHAT_AI_ASSISTANT_ENABLED:
        raise ChatAIError('APPLICATION_UNAVAILABLE')
    user = CustomUser.objects.filter(pk=executor.user_id, is_active=True).first()
    if user is None:
        raise ChatAIError('NOT_AUTHENTICATED')
    stock_superuser = resource.startswith('stock_') and user.is_superuser
    if not stock_superuser and not Membership.objects.filter(user=user, company_id=company_id).exists():
        raise ChatAIError('PERMISSION_DENIED')
    if not Company.objects.filter(pk=company_id).exists():
        raise ChatAIError('NOT_FOUND')
    return user


def _valid_logistics_line(company_id):
    return (Q(commande__company_id=company_id, client__company_id=company_id,
              article__company_id=company_id, proforma__company_id=company_id,
              proforma__client__company_id=company_id, client_id=F('proforma__client_id'))
            & (Q(expected_emplacement__isnull=True) | Q(expected_emplacement__company_id=company_id))
            & (Q(source_line__isnull=True) | Q(source_line__facture_pro_forma_id=F('proforma_id'),
                                              source_line__article_id=F('article_id'))))


def _logistics_queryset(company_id):
    invalid_lines = LogisticsOrderLine.objects.filter(commande_id=OuterRef('pk')).exclude(_valid_logistics_line(company_id))
    invalid_links = LogisticsOrderProforma.objects.filter(commande_id=OuterRef('pk')).exclude(
        proforma__company_id=company_id, proforma__client__company_id=company_id)
    return LogisticsOrder.objects.filter(company_id=company_id).alias(
        _ai_invalid_line=Exists(invalid_lines), _ai_invalid_link=Exists(invalid_links),
    ).filter(_ai_invalid_line=False, _ai_invalid_link=False)


def scoped_queryset(company_id, resource):
    """Exclude inconsistent related owners before filtering, counting or projection."""
    _adapter(resource)
    company_id = _identifier(company_id)
    if resource == 'logistics_order':
        return _logistics_queryset(company_id)
    if resource == 'stock_balance':
        # The authoritative snapshot helper aggregates incoming orders. If an
        # inconsistent order contributes, suppress that balance rather than leak
        # a derived cross-company quantity or replace the business calculation.
        unsafe_incoming = LogisticsOrderLine.objects.filter(
            commande__company_id=company_id, commande__statut_commande_lancement='Terminée',
            article_id=OuterRef('article_id'), expected_emplacement_id=OuterRef('emplacement_id'),
        ).exclude(commande__statut_global='Annulé').exclude(
            commande__statut__in=INCOMING_EXCLUDED_STATUSES,
        ).exclude(commande_id__in=_logistics_queryset(company_id).values('pk'))
        return StockBalance.objects.filter(company_id=company_id, article__company_id=company_id,
            emplacement__company_id=company_id).select_related('article', 'emplacement').alias(
                _ai_unsafe_incoming=Exists(unsafe_incoming)).filter(_ai_unsafe_incoming=False)
    if resource == 'stock_movement':
        return StockMovement.objects.filter(balance__company_id=company_id,
            balance__article__company_id=company_id, balance__emplacement__company_id=company_id,
        ).select_related('balance__article', 'balance__emplacement')
    if resource == 'stock_receipt':
        invalid_lines = StockReceiptLine.objects.filter(receipt_id=OuterRef('pk')).exclude(
            article__company_id=company_id, emplacement__company_id=company_id,
            logistics_line__commande_id=F('receipt__logistics_order_id'),
            logistics_line__article_id=F('article_id'))
        return StockReceipt.objects.filter(company_id=company_id,
            logistics_order_id__in=_logistics_queryset(company_id).values('pk'),
        ).select_related('logistics_order').alias(_ai_invalid_line=Exists(invalid_lines)).filter(_ai_invalid_line=False)
    invalid_lines = InventoryLine.objects.filter(inventory_id=OuterRef('pk')).exclude(article__company_id=company_id)
    return InventorySession.objects.filter(company_id=company_id, emplacement__company_id=company_id,
        ).select_related('emplacement').alias(_ai_invalid_line=Exists(invalid_lines)).filter(_ai_invalid_line=False)


def _text(value):
    return str(value or '')[:200]


def _iso(value):
    return value.isoformat() if value is not None else None


def card(resource, obj, company_id, snapshots=None):
    adapter = _adapter(resource)
    if not isinstance(obj, adapter.model) or not obj.pk or not scoped_queryset(company_id, resource).filter(pk=obj.pk).exists():
        raise ChatAIError('NOT_FOUND')
    result = {'id': obj.pk, 'date': _iso(getattr(obj, adapter.date_field)), 'navigation': {
        'application': 'facturation', 'resource': resource, 'identifier': obj.pk,
        'company_id': company_id, 'path': f'{adapter.route}{obj.pk}/?company_id={company_id}',
    }}
    if resource == 'stock_balance':
        snapshot = (snapshots if snapshots is not None else prepare_balance_snapshots([obj]))[obj.pk]
        result.update(number=_text(obj.article.reference), product_name=_text(obj.article.designation),
                      location=_text(obj.emplacement.nom), status=snapshot['stock_state'])
        result.update({key: str(value) for key, value in snapshot.items() if key != 'stock_state'})
    elif resource == 'stock_movement':
        result.update(number=_text(obj.balance.article.reference), product_name=_text(obj.balance.article.designation),
                      location=_text(obj.balance.emplacement.nom), status=obj.movement_type,
                      quantity=str(obj.quantity), balance_after=str(obj.balance_after))
    elif resource == 'stock_receipt':
        result.update(number=_text(obj.reference) or f'Réception {obj.pk}', status=obj.status,
                      logistics_number=_text(obj.logistics_order.numero_commande), supplier=_text(obj.logistics_order.fournisseur),
                      date_validated=_iso(obj.date_validated))
    elif resource == 'stock_inventory':
        result.update(number=_text(obj.reference) or f'Inventaire {obj.pk}', status=obj.status,
                      location=_text(obj.emplacement.nom), date_validated=_iso(obj.date_validated))
    else:
        result.update(number=_text(obj.numero_commande), supplier=_text(obj.fournisseur), status=obj.statut,
                      global_status=obj.calculate_global_status(), date_expected=_iso(obj.date_prevue),
                      date_received=_iso(obj.date_reelle))
    return result


def _arguments(resource, args):
    adapter = _adapter(resource)
    if set(args) - (adapter.filters | {'status', 'date_from', 'date_to', 'limit', 'offset'}):
        raise ChatAIError('INVALID_ARGUMENTS')
    cleaned = dict(args)
    for field in adapter.filters | {'status'}:
        if field in cleaned:
            if not isinstance(cleaned[field], str) or len(cleaned[field]) > 120 or '\x00' in cleaned[field]:
                raise ChatAIError('INVALID_ARGUMENTS')
            cleaned[field] = cleaned[field].strip()
    if cleaned.get('status') and cleaned['status'] not in adapter.statuses:
        raise ChatAIError('INVALID_ARGUMENTS')
    for field in ('date_from', 'date_to'):
        if field in cleaned:
            try:
                value = cleaned[field]
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError()
                cleaned[field] = date.fromisoformat(value)
            except ValueError as exc:
                raise ChatAIError('INVALID_ARGUMENTS') from exc
    start, end = cleaned.get('date_from'), cleaned.get('date_to')
    if start and end and (start > end or (end - start).days > 3660):
        raise ChatAIError('INVALID_ARGUMENTS')
    limit, offset = cleaned.get('limit', 10), cleaned.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= 10 or type(offset) is not int or not 0 <= offset <= 1000:
        raise ChatAIError('INVALID_ARGUMENTS')
    return cleaned, limit, offset


def _terms(prefix, fields, value):
    terms = Q()
    for field in fields:
        terms |= Q(**{prefix + field + '__icontains': value})
    return terms


def _filtered(queryset, resource, args):
    filters = Q()
    if resource in ('stock_balance', 'stock_movement'):
        prefix = '' if resource == 'stock_balance' else 'balance__'
        if args.get('reference'):
            filters &= Q(**{prefix + 'article__reference__icontains': args['reference']})
        if args.get('product_name'):
            filters &= _terms(prefix + 'article__', ('reference', 'designation'), args['product_name'])
        if args.get('location_name'):
            filters &= Q(**{prefix + 'emplacement__nom__icontains': args['location_name']})
    else:
        reference_fields = ('numero_commande',) if resource == 'logistics_order' else ('reference',)
        if args.get('reference'):
            filters &= _terms('', reference_fields, args['reference'])
        line_prefix = 'lignes__' if resource == 'logistics_order' else 'lines__'
        if args.get('product_name'):
            filters &= _terms(line_prefix + 'article__', ('reference', 'designation'), args['product_name'])
        if args.get('location_name'):
            location_field = {'logistics_order': 'lignes__expected_emplacement__nom__icontains',
                              'stock_receipt': 'lines__emplacement__nom__icontains',
                              'stock_inventory': 'emplacement__nom__icontains'}[resource]
            filters &= Q(**{location_field: args['location_name']})
        if args.get('client_name'):
            client_prefix = 'lignes__client__' if resource == 'logistics_order' else 'lines__logistics_line__client__'
            filters &= _terms(client_prefix, ('raison_sociale', 'nom', 'prenom'), args['client_name'])
        if args.get('supplier_name'):
            supplier_field = 'fournisseur__icontains' if resource == 'logistics_order' else 'logistics_order__fournisseur__icontains'
            filters &= Q(**{supplier_field: args['supplier_name']})
    if args.get('status'):
        status = args['status']
        if resource == 'stock_balance':
            queryset = queryset.alias(_ai_available=F('physical_quantity') - F('reserved_quantity'))
            if status == 'a_approvisionner':
                filters &= Q(_ai_available__lt=0)
            elif status == 'minimum':
                filters &= Q(article__stock_minimum__gt=0, _ai_available__gte=0, _ai_available__lte=F('article__stock_minimum'))
            else:
                filters &= Q(article__stock_minimum=0, _ai_available__gte=0) | Q(_ai_available__gt=F('article__stock_minimum'))
        else:
            field = {'stock_movement': 'movement_type', 'logistics_order': 'statut'}.get(resource, 'status')
            filters &= Q(**{field: status})
    for input_field, lookup in (('date_from', 'gte'), ('date_to', 'lte')):
        if args.get(input_field):
            filters &= Q(**{OPERATIONS[resource].date_field + '__date__' + lookup: args[input_field]})
    return queryset.filter(filters).distinct()


def search(executor, resource, **args):
    args, limit, offset = _arguments(resource, args)
    authorize(executor, resource)
    qs = _filtered(scoped_queryset(executor.company_id, resource), resource, args)
    rows = list(qs.order_by('-' + OPERATIONS[resource].date_field, '-pk')[offset:offset + limit + 1])
    rows_to_show = rows[:limit]
    snapshots = prepare_balance_snapshots(rows_to_show) if resource == 'stock_balance' else None
    items = [card(resource, obj, executor.company_id, snapshots) for obj in rows_to_show]
    authorize(executor, resource)
    executor.save_results(resource, items)
    more = len(rows) > limit
    return {'type': 'record_list', 'resource': resource, 'items': items, 'has_more': more,
            'next_offset': offset + limit if more and offset + limit <= 1000 else None}


def detail(executor, resource, identifier):
    _identifier(identifier)
    authorize(executor, resource)
    obj = scoped_queryset(executor.company_id, resource).filter(pk=identifier).first()
    if obj is None:
        raise ChatAIError('NOT_FOUND')
    item = card(resource, obj, executor.company_id)
    if resource in ('stock_receipt', 'stock_inventory', 'logistics_order'):
        relation = obj.lignes if resource == 'logistics_order' else obj.lines
        related = ('article', 'client', 'expected_emplacement') if resource == 'logistics_order' else (
            ('article', 'emplacement') if resource == 'stock_receipt' else ('article',))
        rows = list(relation.select_related(*related).order_by('pk')[:11])
        lines = []
        for line in rows[:10]:
            entry = {'id': line.pk, 'reference': _text(line.article.reference), 'product_name': _text(line.article.designation)}
            if resource == 'stock_inventory':
                entry.update(expected_quantity=str(line.expected_quantity), counted_quantity=str(line.counted_quantity))
            else:
                entry['quantity'] = str(line.quantity)
                if resource == 'stock_receipt':
                    entry['location'] = _text(line.emplacement.nom)
                else:
                    entry.update(client=_text(line.client), received_quantity=str(line.received_quantity),
                                 location=_text(line.expected_emplacement.nom) if line.expected_emplacement_id else None)
            lines.append(entry)
        item.update(lines=lines, has_more_lines=len(rows) > 10)
    authorize(executor, resource)
    if not scoped_queryset(executor.company_id, resource).filter(pk=identifier).exists():
        raise ChatAIError('NOT_FOUND')
    executor.save_results(resource, [item])
    return {'type': 'record_list', 'resource': resource, 'items': [item]}
