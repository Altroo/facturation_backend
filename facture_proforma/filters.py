import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value, F, FloatField
from django.db.utils import DatabaseError

from .models import FactureProForma


class FactureProFormaFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    statut = django_filters.CharFilter(method="filter_statut", label="Status")
    client_id = django_filters.NumberFilter(field_name="client__id", label="Client ID")

    class Meta:
        model = FactureProForma
        fields = ["statut", "client_id"]

    @staticmethod
    def filter_statut(queryset, _name, value):
        if not value:
            return queryset
        return queryset.filter(statut__iexact=value.strip())

    @staticmethod
    def global_search(queryset, _name, value):
        if not value or not value.strip():
            return queryset

        value = value.strip()

        # detect tsquery metacharacters in lowercase and skip FTS if present
        ts_meta = set(":*?&|!()<>")
        skip_fts = any(ch in ts_meta for ch in value.lower())

        search_vector = (
            SearchVector("numero_facture", weight="A")
            + SearchVector("client__raison_sociale", weight="A")
            + SearchVector("numero_bon_commande_client", weight="B")
        )

        queryset_with_vector = queryset.annotate(_search=search_vector)

        if not skip_fts:
            try:
                search_query = SearchQuery(value, search_type="plain")
                fts_results = queryset_with_vector.filter(
                    _search=search_query
                ).annotate(_rank=SearchRank(F("_search"), search_query))
            except DatabaseError:
                fts_results = queryset.none().annotate(
                    _rank=Value(0.0, output_field=FloatField())
                )
        else:
            fts_results = queryset.none().annotate(
                _rank=Value(0.0, output_field=FloatField())
            )

        fallback_q = (
            Q(numero_facture__icontains=value)
            | Q(client__raison_sociale__icontains=value)
            | Q(numero_bon_commande_client__icontains=value)
        )

        fallback_results = queryset.filter(fallback_q).annotate(
            _rank=Value(0.0, output_field=FloatField())
        )

        return (fts_results | fallback_results).distinct().order_by("-_rank")
