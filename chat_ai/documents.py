"""Fixed, scoped read adapters for verified Facturation document modules.

Authorization belongs to the executor; this module never accepts model classes,
field names, tenant IDs, serializer names, or raw filter expressions from a model.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

from django.db.models import Model, Q, QuerySet
from django_filters import FilterSet
from rest_framework.serializers import BaseSerializer

from bon_de_livraison.filters import BonDeLivraisonFilter
from bon_de_livraison.models import BonDeLivraison
from bon_de_livraison.serializers import BonDeLivraisonDetailSerializer
from facture_avoir.filters import FactureAvoirFilter
from facture_avoir.models import FactureAvoir
from facture_avoir.serializers import FactureAvoirDetailSerializer
from facture_proforma.filters import FactureProFormaFilter
from facture_proforma.models import FactureProForma
from facture_proforma.serializers import FactureProformaDetailSerializer
from chat_ai_assistant.contracts import ChatAIError

from .navigation import ChatAINavigationResolver


@dataclass(frozen=True)
class DocumentAdapter:
    model: type[Model]
    filter_class: type[FilterSet]
    serializer_class: type[BaseSerializer]
    number_field: str
    date_field: str
    editable_fields: frozenset[str]


DOCUMENTS = MappingProxyType({
    'proforma': DocumentAdapter(
        FactureProForma, FactureProFormaFilter, FactureProformaDetailSerializer,
        'numero_facture', 'date_facture',
        frozenset({'remarque', 'termes_paiement', 'date_echeance'}),
    ),
    'credit_note': DocumentAdapter(
        FactureAvoir, FactureAvoirFilter, FactureAvoirDetailSerializer,
        'numero_avoir', 'date_avoir', frozenset({'remarque'}),
    ),
    'delivery_note': DocumentAdapter(
        BonDeLivraison, BonDeLivraisonFilter, BonDeLivraisonDetailSerializer,
        'numero_bon_livraison', 'date_bon_livraison',
        frozenset({'remarque', 'date_echeance'}),
    ),
})


def _adapter(resource):
    if not isinstance(resource, str) or resource not in DOCUMENTS:
        raise ChatAIError('INVALID_ARGUMENTS')
    return DOCUMENTS[resource]


def _company_id(company_id):
    if type(company_id) is not int or not 1 <= company_id <= 2147483647:
        raise ChatAIError('INVALID_ARGUMENTS')
    return company_id


def scoped_queryset(company_id, resource) -> QuerySet:
    """Only consistent documents in this trusted company, including related owners."""
    adapter = _adapter(resource)
    company_id = _company_id(company_id)
    queryset = adapter.model.objects.filter(
        company_id=company_id, client__company_id=company_id,
    ).select_related('client')
    if resource == 'credit_note':
        queryset = queryset.filter(
            Q(facture_origine__isnull=True)
            | Q(facture_origine__company_id=company_id,
                facture_origine__client__company_id=company_id)
        ).select_related('facture_origine__client')
    return queryset


def card(resource, obj, company_id):
    """Project the same minimal fields as invoice/quote results; never serialize notes."""
    adapter = _adapter(resource)
    company_id = _company_id(company_id)
    if (not isinstance(obj, adapter.model) or not obj.pk
            or obj.company_id != company_id or obj.client.company_id != company_id):
        raise ChatAIError('NOT_FOUND')
    if resource == 'credit_note' and obj.facture_origine_id:
        origin = obj.facture_origine
        if origin.company_id != company_id or origin.client.company_id != company_id:
            raise ChatAIError('NOT_FOUND')
    return {
        'id': obj.pk,
        'number': getattr(obj, adapter.number_field),
        'client': str(obj.client)[:200],
        'date': getattr(obj, adapter.date_field).isoformat(),
        'status': obj.statut,
        'currency': obj.devise,
        'total_ttc': str(obj.total_ttc_apres_remise),
        'navigation': ChatAINavigationResolver.resolve(resource, company_id, obj.pk),
    }


def search(executor, resource, **args):
    """Bounded natural-name search, after fresh authorization on the trusted executor."""
    from .tools import parse_dates

    adapter = _adapter(resource)
    allowed = {'document_number', 'client_name', 'product_name', 'date_from', 'date_to', 'limit', 'offset'}
    if set(args) - allowed:
        raise ChatAIError('INVALID_ARGUMENTS')
    for field in ('document_number', 'client_name', 'product_name'):
        if field in args and (not isinstance(args[field], str) or len(args[field]) > 120):
            raise ChatAIError('INVALID_ARGUMENTS')
    for field in ('date_from', 'date_to'):
        if field in args and (not isinstance(args[field], str)
                              or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args[field])):
            raise ChatAIError('INVALID_ARGUMENTS')
    limit, offset = args.get('limit', 10), args.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= 10 or type(offset) is not int or not 0 <= offset <= 1000:
        raise ChatAIError('INVALID_ARGUMENTS')
    start, end = parse_dates(args)
    executor.authorize()
    queryset = scoped_queryset(executor.company_id, resource)
    filters = {}
    if args.get('document_number'):
        filters[adapter.number_field] = args['document_number'].strip()
    if args.get('client_name'):
        filters['client_name__icontains'] = args['client_name'].strip()
    if start:
        filters['date_after'] = start
    if end:
        filters['date_before'] = end
    filterset = adapter.filter_class(filters, queryset=queryset)
    if not filterset.is_valid():
        raise ChatAIError('INVALID_ARGUMENTS')
    queryset = filterset.qs
    product = args.get('product_name', '').strip()
    if product:
        queryset = queryset.filter(
            Q(lignes__article__designation__icontains=product)
            | Q(lignes__article__reference__icontains=product),
            lignes__article__company_id=executor.company_id,
        ).distinct()
    records = list(queryset.order_by('-' + adapter.date_field, '-pk')[offset:offset + limit + 1])
    items = [card(resource, obj, executor.company_id) for obj in records[:limit]]
    executor.authorize()
    executor.save_results(resource, items)
    return {
        'type': 'record_list', 'resource': resource, 'items': items,
        'has_more': len(records) > limit,
        'next_offset': offset + limit if len(records) > limit and offset + limit <= 1000 else None,
    }
