import django_filters
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q, Value
from django.db.models.functions import Coalesce

from .models import Devi, DeviLine


class DeviFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    statut = django_filters.CharFilter(method="filter_statut", label="Status")
    client_id = django_filters.NumberFilter(field_name="client__id", label="Client ID")

    class Meta:
        model = Devi
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

        search_vector = (
            SearchVector("numero_devis", weight="A")
            + SearchVector("client__raison_sociale", weight="A")
            + SearchVector("numero_demande_prix_client", weight="B")
        )
        search_query = SearchQuery(value.strip(), search_type="plain")

        fallback_q = (
            Q(numero_devis__icontains=value)
            | Q(client__raison_sociale__icontains=value)
            | Q(numero_demande_prix_client__icontains=value)
        )

        combined_results = (
            queryset.annotate(
                _rank=Coalesce(SearchRank(search_vector, search_query), Value(0.0))
            )
            .filter(Q(_rank__gte=0.001) | fallback_q)
            .distinct()
            .order_by("-_rank")
        )

        return combined_results


class DeviLineFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="global_search", label="Search")
    devis_id = django_filters.NumberFilter(field_name="devis__id", label="Devi ID")

    class Meta:
        model = DeviLine
        fields = ["devis_id"]

    @staticmethod
    def global_search(queryset, _name, value):
        if not value or not value.strip():
            return queryset

        # search on article fields (designation / reference) which exist
        search_vector = SearchVector("article__designation", weight="A") + SearchVector(
            "article__reference", weight="A"
        )
        search_query = SearchQuery(value.strip(), search_type="plain")

        fallback_q = Q(article__designation__icontains=value) | Q(
            article__reference__icontains=value
        )

        combined_results = (
            queryset.annotate(
                _rank=Coalesce(SearchRank(search_vector, search_query), Value(0.0))
            )
            .filter(Q(_rank__gte=0.001) | fallback_q)
            .distinct()
            .order_by("-_rank")
        )

        return combined_results
