"""Bounded read adapters for articles, payments, and native staff-only users.

Public API mirrors documents.py. User queryset/card calls additionally require
trusted ``user_id``. ``search`` and ``get`` reauthorize before and after reading.
Conversation ownership/company authorization remains the caller's responsibility;
user administration itself has the application's global, staff-only read scope.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

from django.conf import settings
from django.db.models import Model, Q, QuerySet
from django_filters import FilterSet

from account.filters import UsersFilter
from account.models import CustomUser
from article.filters import ArticleFilter
from article.models import Article
from core.nectar import is_nectar_company_id
from reglement.filters import ReglementFilter
from reglement.models import Reglement
from chat_ai_assistant.contracts import ChatAIError

from .navigation import ChatAINavigationResolver


@dataclass(frozen=True)
class CatalogAdapter:
    model: type[Model]
    filter_class: type[FilterSet]
    date_field: str
    arguments: frozenset[str]


_COMMON = frozenset({'query', 'date_from', 'date_to', 'limit', 'offset'})
CATALOG = MappingProxyType({
    'article': CatalogAdapter(Article, ArticleFilter, 'date_created', _COMMON | {
        'reference', 'product_name', 'type_article', 'archived'}),
    'payment': CatalogAdapter(Reglement, ReglementFilter, 'date_reglement', _COMMON | {
        'invoice_number', 'client_name', 'product_name', 'status'}),
    'user': CatalogAdapter(CustomUser, UsersFilter, 'date_joined', _COMMON | {
        'name', 'email', 'is_active'}),
})


def _adapter(resource):
    if not isinstance(resource, str) or resource not in CATALOG:
        raise ChatAIError('INVALID_ARGUMENTS')
    return CATALOG[resource]


def _identifier(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise ChatAIError('INVALID_ARGUMENTS')
    return value


def _staff(user_id):
    """Fresh native IsAdminUser check; never trust cached request/user attributes."""
    if not settings.CHAT_AI_ASSISTANT_ENABLED:
        raise ChatAIError('APPLICATION_UNAVAILABLE')
    user = CustomUser.objects.filter(pk=_identifier(user_id), is_active=True).only('is_staff').first()
    if user is None:
        raise ChatAIError('NOT_AUTHENTICATED')
    if not user.is_staff:
        raise ChatAIError('PERMISSION_DENIED')
    return user


def authorize(executor, resource):
    _adapter(resource)
    if resource == 'user':
        return _staff(executor.user_id)
    return executor.authorize()


def scoped_queryset(company_id, resource, *, user_id=None) -> QuerySet:
    """Fixed owner predicates. As in documents.py, caller authorizes company reads."""
    _adapter(resource)
    if resource == 'user':
        _staff(user_id)
        return CustomUser.objects.exclude(pk=user_id)
    company_id = _identifier(company_id)
    if resource == 'article':
        return Article.objects.filter(company_id=company_id)
    return Reglement.objects.filter(
        facture_client__company_id=company_id,
        facture_client__client__company_id=company_id,
    ).select_related('facture_client__client')


def card(resource, obj, company_id, *, user_id=None):
    """Small explicit projections; no serializers, freeform notes, or credentials."""
    adapter = _adapter(resource)
    if not isinstance(obj, adapter.model) or not obj.pk:
        raise ChatAIError('NOT_FOUND')
    if resource == 'user':
        _staff(user_id)
        if obj.pk == user_id:
            raise ChatAIError('NOT_FOUND')
        item = {'id': obj.pk, 'name': f'{obj.first_name} {obj.last_name}'.strip()[:200], 'email': obj.email[:254],
                'is_active': obj.is_active, 'is_staff': obj.is_staff}
    elif resource == 'article':
        if obj.company_id != _identifier(company_id):
            raise ChatAIError('NOT_FOUND')
        item = {'id': obj.pk, 'number': obj.reference[:100], 'designation': obj.designation[:300],
                'type_article': obj.type_article, 'archived': obj.archived,
                'sale_amount': str(obj.prix_vente), 'sale_currency': obj.devise_prix_vente,
                'purchase_amount': str(obj.prix_achat), 'purchase_currency': obj.devise_prix_achat}
        if is_nectar_company_id(company_id):
            item['sale_label'] = 'price_excl_tax'
            # Match Nectar's actual article form, which does not show purchase price.
            item.pop('purchase_amount')
            item.pop('purchase_currency')
    else:
        company_id = _identifier(company_id)
        invoice = obj.facture_client
        if invoice.company_id != company_id or invoice.client.company_id != company_id:
            raise ChatAIError('NOT_FOUND')
        item = {'id': obj.pk, 'number': invoice.numero_facture[:100],
                'client': str(invoice.client)[:200], 'date': obj.date_reglement.isoformat(),
                'status': obj.statut, 'amount': str(obj.montant), 'currency': invoice.devise}
    item['navigation'] = ChatAINavigationResolver.resolve(resource, company_id, obj.pk)
    return item


def _arguments(resource, args):
    from .tools import parse_dates

    adapter = _adapter(resource)
    if set(args) - adapter.arguments:
        raise ChatAIError('INVALID_ARGUMENTS')
    values = dict(args)
    for field, value in values.items():
        if field in {'limit', 'offset'}:
            continue
        if field in {'archived', 'is_active'}:
            if type(value) is not bool:
                raise ChatAIError('INVALID_ARGUMENTS')
        elif field in {'date_from', 'date_to'}:
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ChatAIError('INVALID_ARGUMENTS')
        else:
            if not isinstance(value, str) or not value.strip() or len(value) > 120 or '\x00' in value:
                raise ChatAIError('INVALID_ARGUMENTS')
            values[field] = value.strip()
    if 'type_article' in values and values['type_article'] not in {'Produit', 'Service'}:
        raise ChatAIError('INVALID_ARGUMENTS')
    if 'status' in values and values['status'] not in {'Valide', 'Annulé'}:
        raise ChatAIError('INVALID_ARGUMENTS')
    limit, offset = values.get('limit', 10), values.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= 10 or type(offset) is not int or not 0 <= offset <= 1000:
        raise ChatAIError('INVALID_ARGUMENTS')
    start, end = parse_dates(values)
    return adapter, values, limit, offset, start, end


def _words(queryset, value, fields):
    """Match full natural names across first/last/company names, token by token."""
    for word in value.split():
        condition = Q()
        for field in fields:
            condition |= Q(**{field + '__icontains': word})
        queryset = queryset.filter(condition)
    return queryset


def search(executor, resource, **args):
    adapter, args, limit, offset, start, end = _arguments(resource, args)
    authorize(executor, resource)
    queryset = scoped_queryset(executor.company_id, resource, user_id=executor.user_id)
    mappings = {
        'article': {'reference': 'reference', 'type_article': 'type_article', 'archived': 'archived'},
        'payment': {'invoice_number': 'facture_client_numero', 'status': 'statut'},
        'user': {'email': 'email__icontains', 'is_active': 'is_active'},
    }
    filters = {target: args[source] for source, target in mappings[resource].items() if source in args}
    filterset = adapter.filter_class(filters, queryset=queryset)
    if not filterset.is_valid():
        raise ChatAIError('INVALID_ARGUMENTS')
    queryset = filterset.qs
    if resource == 'article':
        for field in ('query', 'product_name'):
            if args.get(field):
                queryset = _words(queryset, args[field], ('reference', 'designation'))
    elif resource == 'payment':
        client_fields = ('facture_client__client__raison_sociale', 'facture_client__client__nom',
                         'facture_client__client__prenom')
        if args.get('client_name'):
            queryset = _words(queryset, args['client_name'], client_fields)
        if args.get('query'):
            queryset = _words(queryset, args['query'], ('facture_client__numero_facture',) + client_fields)
        if args.get('product_name'):
            # One filter call keeps ownership and text predicates on the SAME line.
            product = args['product_name']
            queryset = queryset.filter(
                Q(facture_client__lignes__article__designation__icontains=product)
                | Q(facture_client__lignes__article__reference__icontains=product),
                facture_client__lignes__article__company_id=executor.company_id,
            ).distinct()
    else:
        for field in ('query', 'name'):
            if args.get(field):
                fields = ('first_name', 'last_name', 'email') if field == 'query' else ('first_name', 'last_name')
                queryset = _words(queryset, args[field], fields)
    # DateTime fields use the application's timezone and include the whole final day.
    date_field = adapter.date_field + ('__date' if resource in {'article', 'user'} else '')
    if start:
        queryset = queryset.filter(**{date_field + '__gte': start})
    if end:
        queryset = queryset.filter(**{date_field + '__lte': end})
    records = list(queryset.order_by('-' + adapter.date_field, '-pk')[offset:offset + limit + 1])
    items = [card(resource, obj, executor.company_id, user_id=executor.user_id) for obj in records[:limit]]
    authorize(executor, resource)
    executor.save_results(resource, items)
    return {'type': 'record_list', 'resource': resource, 'items': items,
            'has_more': len(records) > limit,
            'next_offset': offset + limit if len(records) > limit and offset + limit <= 1000 else None}


def get(executor, resource, identifier):
    """Resolve one authorized record; foreign, self-user and missing IDs stay NOT_FOUND."""
    _adapter(resource)
    identifier = _identifier(identifier)
    authorize(executor, resource)
    obj = scoped_queryset(executor.company_id, resource, user_id=executor.user_id).filter(pk=identifier).first()
    if obj is None:
        raise ChatAIError('NOT_FOUND')
    item = card(resource, obj, executor.company_id, user_id=executor.user_id)
    authorize(executor, resource)
    executor.save_results(resource, [item])
    return {'type': 'record_list', 'resource': resource, 'items': [item],
            'has_more': False, 'next_offset': None}
